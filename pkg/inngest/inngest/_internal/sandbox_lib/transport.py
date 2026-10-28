"""
HTTP transports that drive sandbox operations.

Both transports authenticate with the client's hashed signing key, retry once
with the fallback key after a 401 or 403, and map failures to SandboxError. In
Dev Server mode no key is needed: the Dev Server forwards sandbox requests to
Inngest Cloud with the developer's `inngest login` credentials.
"""

from __future__ import annotations

import asyncio
import contextlib
import http
import json
import threading
import time
import typing
import urllib.parse

import httpx

from inngest._internal import net, server_lib, transforms

from . import errors as sandbox_errors
from . import models, ops
from .errors import SandboxAction, SandboxError, SandboxValidationError

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib

T = typing.TypeVar("T")

_TIMEOUT: typing.Final = httpx.Timeout(60.0, connect=10.0)
_STREAM_TIMEOUT: typing.Final = httpx.Timeout(60.0, connect=10.0, read=None)
_UPLOAD_CHUNK_BYTES: typing.Final = 1024 * 1024
_AUTH_FAILED: typing.Final = (
    http.HTTPStatus.UNAUTHORIZED,
    http.HTTPStatus.FORBIDDEN,
)

UploadData: typing.TypeAlias = (
    bytes
    | bytearray
    | memoryview
    | str
    | typing.IO[bytes]
    | typing.AsyncIterable[bytes]
)
UploadDataSync: typing.TypeAlias = (
    bytes
    | bytearray
    | memoryview
    | str
    | typing.IO[bytes]
    | typing.Iterable[bytes]
)


@typing.runtime_checkable
class _Readable(typing.Protocol):
    def read(self, size: int = ..., /) -> bytes: ...


class _Base:
    def __init__(self, client: client_lib.Inngest) -> None:
        self._client = client

    def _keys(self) -> tuple[str | None, str | None]:
        """
        Hashed signing key and fallback key.
        """

        def hashed(key: str | None, name: str) -> str | None:
            if key is None or key.strip() == "":
                return None
            try:
                return transforms.hash_signing_key(key.strip())
            except ValueError:
                raise SandboxValidationError(f"invalid {name}") from None

        key = hashed(self._client.signing_key, "signing key")
        fallback = hashed(
            self._client.signing_key_fallback, "fallback signing key"
        )
        if (
            key is None
            and self._client._mode != server_lib.ServerKind.DEV_SERVER
        ):
            raise SandboxValidationError(
                "A signing key is required to use sandboxes; set INNGEST_SIGNING_KEY"
            )
        return key, fallback

    def _headers(
        self, key: str | None, content_type: str | None
    ) -> dict[str, str]:
        headers = net.create_headers(
            env=self._client.env, framework=None, server_kind=None
        )
        content_type_key = server_lib.HeaderKey.CONTENT_TYPE.value
        if content_type is None:
            headers.pop(content_type_key, None)
        else:
            headers[content_type_key] = content_type
        if key is not None:
            headers[server_lib.HeaderKey.AUTHORIZATION.value] = f"Bearer {key}"
        return headers

    def _url(self, path: str) -> str:
        return urllib.parse.urljoin(self._client.api_origin, path)


def _ids(req: ops.Request) -> dict[str, str | None]:
    return {
        "sandbox_id": req.sandbox_id,
        "process_id": req.process_id,
        "snapshot_id": req.snapshot_id,
    }


def _timeout(req: ops.Request) -> httpx.Timeout:
    if req.timeout is None:
        return _TIMEOUT
    return httpx.Timeout(max(req.timeout, 60.0), connect=10.0)


def _request_id(res: httpx.Response) -> str | None:
    return res.headers.get(server_lib.HeaderKey.REQUEST_ID.value) or None


def _transport_failure(
    action: SandboxAction,
    ids: dict[str, str | None],
    *,
    sent: bool = True,
) -> SandboxError:
    return sandbox_errors.transport_failure(
        action,
        sent=sent,
        sandbox_id=ids.get("sandbox_id"),
        process_id=ids.get("process_id"),
        snapshot_id=ids.get("snapshot_id"),
    )


def _request_failure(
    action: SandboxAction,
    err: httpx.RequestError,
    ids: dict[str, str | None],
) -> SandboxError:
    # These fail before any of the request is sent.
    sent = not isinstance(
        err, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
    )
    return _transport_failure(action, ids, sent=sent)


def _response_error(
    action: SandboxAction,
    res: httpx.Response,
    body: bytes,
    ids: dict[str, str | None],
) -> SandboxError:
    code = sandbox_errors.SandboxErrorCode.INTERNAL_ERROR.value
    message = f"Sandbox API returned HTTP {res.status_code}"
    details: list[dict[str, object]] = []
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    items = parsed.get("errors") if isinstance(parsed, dict) else None
    if (
        isinstance(items, list)
        and len(items) > 0
        and isinstance(items[0], dict)
        and isinstance(items[0].get("code"), str)
        and isinstance(items[0].get("message"), str)
        and items[0]["code"] != ""
    ):
        code = items[0]["code"]
        message = items[0]["message"] or message
        details = [item for item in items if isinstance(item, dict)]

    return sandbox_errors.from_api_error(
        action,
        status=res.status_code,
        code=code,
        message=message,
        sandbox_id=ids.get("sandbox_id"),
        process_id=ids.get("process_id"),
        snapshot_id=ids.get("snapshot_id"),
        request_id=_request_id(res),
        details=details,
    )


def _envelope(
    req: ops.Request, res: httpx.Response, body: bytes
) -> ops.Response:
    if res.status_code == http.HTTPStatus.NO_CONTENT:
        return ops.Response(status=res.status_code)
    try:
        parsed = json.loads(body)
    except ValueError:
        raise _transport_failure(req.action, _ids(req)) from None
    if not isinstance(parsed, dict):
        raise SandboxValidationError("Invalid sandbox API response")
    return ops.Response(
        status=res.status_code,
        data=parsed.get("data"),
        metadata=parsed.get("metadata"),
        page=parsed.get("page"),
    )


def _json_body(req: ops.Request) -> bytes | None:
    if req.body is None:
        return None
    return json.dumps(req.body).encode("utf-8")


def _frame(
    line: str,
    action: SandboxAction,
    status: int,
    request_id: str | None,
    ids: dict[str, str | None],
) -> models.SandboxOutputChunk | None:
    line = line.strip()
    if line == "":
        return None
    try:
        frame = json.loads(line)
    except ValueError:
        raise SandboxValidationError(
            "Sandbox API returned an invalid stream frame"
        ) from None
    if not isinstance(frame, dict):
        raise SandboxValidationError(
            "Sandbox API returned an invalid stream frame"
        )
    if frame.get("type") == "error":
        item = frame.get("error")
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("code"), str)
            or not isinstance(item.get("message"), str)
        ):
            raise SandboxValidationError(
                "Sandbox API returned an invalid stream error"
            )
        raise sandbox_errors.from_api_error(
            action,
            status=status,
            code=item["code"],
            message=item["message"],
            sandbox_id=ids.get("sandbox_id"),
            process_id=ids.get("process_id"),
            snapshot_id=ids.get("snapshot_id"),
            request_id=request_id,
        )
    if frame.get("type") != "log":
        raise SandboxValidationError(
            "Sandbox API returned an invalid stream frame"
        )
    return ops.decode_chunk(frame)


def _check_download(
    res: httpx.Response,
    body: bytes,
    sandbox_id: str,
) -> bytes:
    # A transfer that fails midway still has HTTP 200 and a short body.
    expected = res.headers.get("content-length")
    if (
        expected is not None
        and expected.isdigit()
        and int(expected) != len(body)
    ):
        raise SandboxError(
            action="file.download",
            code=sandbox_errors.SandboxErrorCode.COMPUTE_UNAVAILABLE.value,
            message=f"Sandbox file download ended after {len(body)} of {expected} bytes. Repeating the download is safe",
            status=res.status_code,
            sandbox_id=sandbox_id,
            retryable=True,
            request_id=_request_id(res),
        )
    return body


async def _stream_error(
    action: SandboxAction,
    res: httpx.Response,
    ids: dict[str, str | None],
) -> SandboxError:
    try:
        body = await res.aread()
    except httpx.RequestError:
        return _transport_failure(action, ids)
    return _response_error(action, res, body, ids)


def _stream_error_sync(
    action: SandboxAction,
    res: httpx.Response,
    ids: dict[str, str | None],
) -> SandboxError:
    try:
        body = res.read()
    except httpx.RequestError:
        return _transport_failure(action, ids)
    return _response_error(action, res, body, ids)


def _file_query(path: str, mode: str | None) -> dict[str, str]:
    query = {"path": path}
    if mode is not None:
        query["mode"] = mode
    return query


class SandboxTransport(_Base):
    """
    Async transport. Keeps one HTTP client per event loop, since an
    httpx.AsyncClient can't be shared across loops.
    """

    def __init__(
        self,
        client: client_lib.Inngest,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(client)
        self._http_transport = http_transport
        self._clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
        self._lock = threading.Lock()

    def _http(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        with self._lock:
            # A client references its loop, so a weak mapping would never drop
            # it. Drop clients whose loop has closed, like each asyncio.run's.
            for closed in [k for k in self._clients if k.is_closed()]:
                del self._clients[closed]
            http_client = self._clients.get(loop)
            if http_client is None or http_client.is_closed:
                http_client = httpx.AsyncClient(
                    transport=self._http_transport, timeout=_TIMEOUT
                )
                self._clients[loop] = http_client
            return http_client

    async def run(self, op: ops.Op[T]) -> T:
        """
        Drive an operation to completion.
        """

        sent: ops.Response | None = None
        thrown: SandboxError | None = None
        while True:
            try:
                command = op.send(sent) if thrown is None else op.throw(thrown)
            except StopIteration as stop:
                return typing.cast(T, stop.value)
            sent, thrown = None, None
            if isinstance(command, ops.Sleep):
                await asyncio.sleep(command.seconds)
                continue
            try:
                sent = await self._json(command)
            except SandboxError as err:
                thrown = err

    async def _send(
        self,
        action: SandboxAction,
        method: str,
        path: str,
        *,
        ids: dict[str, str | None],
        query: dict[str, str] | None = None,
        content: bytes | typing.AsyncIterable[bytes] | None = None,
        content_type: str | None = None,
        timeout: httpx.Timeout = _TIMEOUT,
        stream: bool = False,
    ) -> httpx.Response:
        key, fallback = self._keys()
        http_client = self._http()

        def build(auth: str | None) -> httpx.Request:
            return http_client.build_request(
                method,
                self._url(path),
                params=query,
                content=content,
                headers=self._headers(auth, content_type),
                timeout=timeout,
            )

        try:
            res = await http_client.send(build(key), stream=stream)
            # A 401 or 403 means nothing ran, so the request can go again with
            # the fallback key. A streamed body can't be sent twice.
            replayable = content is None or isinstance(content, bytes)
            if (
                res.status_code in _AUTH_FAILED
                and fallback is not None
                and replayable
            ):
                await res.aclose()
                res = await http_client.send(build(fallback), stream=stream)
            return res
        except httpx.RequestError as err:
            raise _request_failure(action, err, ids) from err

    async def _json(self, req: ops.Request) -> ops.Response:
        ids = _ids(req)
        body = _json_body(req)
        res = await self._send(
            req.action,
            req.method,
            req.path,
            ids=ids,
            query=req.query,
            content=body,
            content_type=None if body is None else "application/json",
            timeout=_timeout(req),
        )
        content = res.content
        if res.status_code not in req.statuses:
            raise _response_error(req.action, res, content, ids)
        return _envelope(req, res, content)

    async def upload(
        self,
        sandbox_id: str,
        path: str,
        data: UploadData,
        mode: str | None,
    ) -> models.SandboxFileUploadResult:
        content: bytes | typing.AsyncIterable[bytes]
        if isinstance(data, str):
            content = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray, memoryview)):
            content = bytes(data)
        elif isinstance(data, typing.AsyncIterable):
            # Before read(): async files, like aiofiles', have an async read().
            content = data
        else:
            readable = data

            async def read_chunks() -> typing.AsyncIterator[bytes]:
                while chunk := await asyncio.to_thread(
                    readable.read, _UPLOAD_CHUNK_BYTES
                ):
                    yield chunk

            content = read_chunks()

        ids: dict[str, str | None] = {"sandbox_id": sandbox_id}
        res = await self._send(
            "file.upload",
            "PUT",
            f"{ops.sandbox_path(sandbox_id)}/files",
            ids=ids,
            query=_file_query(path, mode),
            content=content,
            content_type="application/octet-stream",
        )
        body = res.content
        if not 200 <= res.status_code < 300:
            raise _response_error("file.upload", res, body, ids)
        envelope = _envelope(
            ops.Request(
                action="file.upload",
                method="PUT",
                path=path,
                statuses=(200,),
                sandbox_id=sandbox_id,
            ),
            res,
            body,
        )
        return models.SandboxFileUploadResult.parse(
            envelope.data, "sandbox file upload result"
        )

    async def download(self, sandbox_id: str, path: str) -> bytes:
        ids: dict[str, str | None] = {"sandbox_id": sandbox_id}
        res = await self._send(
            "file.download",
            "GET",
            f"{ops.sandbox_path(sandbox_id)}/files",
            ids=ids,
            query={"path": path},
        )
        body = res.content
        if not 200 <= res.status_code < 300:
            raise _response_error("file.download", res, body, ids)
        return _check_download(res, body, sandbox_id)

    @contextlib.asynccontextmanager
    async def stream(
        self,
        action: SandboxAction,
        path: str,
        query: dict[str, str],
        *,
        sandbox_id: str,
        process_id: str | None = None,
    ) -> typing.AsyncIterator[typing.AsyncIterator[models.SandboxOutputChunk]]:
        ids: dict[str, str | None] = {
            "sandbox_id": sandbox_id,
            "process_id": process_id,
        }
        res = await self._send(
            action,
            "GET",
            path,
            ids=ids,
            query=query,
            timeout=_STREAM_TIMEOUT,
            stream=True,
        )
        try:
            if not 200 <= res.status_code < 300:
                raise await _stream_error(action, res, ids)

            async def chunks() -> typing.AsyncIterator[
                models.SandboxOutputChunk
            ]:
                request_id = _request_id(res)
                try:
                    async for line in res.aiter_lines():
                        chunk = _frame(
                            line, action, res.status_code, request_id, ids
                        )
                        if chunk is not None:
                            yield chunk
                except httpx.RequestError as err:
                    raise _transport_failure(action, ids) from err

            yield chunks()
        finally:
            await res.aclose()


class SandboxTransportSync(_Base):
    """
    Sync transport.
    """

    def __init__(
        self,
        client: client_lib.Inngest,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(client)
        self._http_client = httpx.Client(
            transport=http_transport, timeout=_TIMEOUT
        )

    def run(self, op: ops.Op[T]) -> T:
        """
        Drive an operation to completion.
        """

        sent: ops.Response | None = None
        thrown: SandboxError | None = None
        while True:
            try:
                command = op.send(sent) if thrown is None else op.throw(thrown)
            except StopIteration as stop:
                return typing.cast(T, stop.value)
            sent, thrown = None, None
            if isinstance(command, ops.Sleep):
                time.sleep(command.seconds)
                continue
            try:
                sent = self._json(command)
            except SandboxError as err:
                thrown = err

    def _send(
        self,
        action: SandboxAction,
        method: str,
        path: str,
        *,
        ids: dict[str, str | None],
        query: dict[str, str] | None = None,
        content: bytes | typing.Iterable[bytes] | None = None,
        content_type: str | None = None,
        timeout: httpx.Timeout = _TIMEOUT,
        stream: bool = False,
    ) -> httpx.Response:
        key, fallback = self._keys()

        def build(auth: str | None) -> httpx.Request:
            return self._http_client.build_request(
                method,
                self._url(path),
                params=query,
                content=content,
                headers=self._headers(auth, content_type),
                timeout=timeout,
            )

        try:
            res = self._http_client.send(build(key), stream=stream)
            replayable = content is None or isinstance(content, bytes)
            if (
                res.status_code in _AUTH_FAILED
                and fallback is not None
                and replayable
            ):
                res.close()
                res = self._http_client.send(build(fallback), stream=stream)
            return res
        except httpx.RequestError as err:
            raise _request_failure(action, err, ids) from err

    def _json(self, req: ops.Request) -> ops.Response:
        ids = _ids(req)
        body = _json_body(req)
        res = self._send(
            req.action,
            req.method,
            req.path,
            ids=ids,
            query=req.query,
            content=body,
            content_type=None if body is None else "application/json",
            timeout=_timeout(req),
        )
        content = res.content
        if res.status_code not in req.statuses:
            raise _response_error(req.action, res, content, ids)
        return _envelope(req, res, content)

    def upload(
        self,
        sandbox_id: str,
        path: str,
        data: UploadDataSync,
        mode: str | None,
    ) -> models.SandboxFileUploadResult:
        content: bytes | typing.Iterable[bytes]
        if isinstance(data, str):
            content = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray, memoryview)):
            content = bytes(data)
        elif isinstance(data, _Readable):
            readable = data

            def read_chunks() -> typing.Iterator[bytes]:
                while chunk := readable.read(_UPLOAD_CHUNK_BYTES):
                    yield chunk

            content = read_chunks()
        else:
            content = data

        ids: dict[str, str | None] = {"sandbox_id": sandbox_id}
        res = self._send(
            "file.upload",
            "PUT",
            f"{ops.sandbox_path(sandbox_id)}/files",
            ids=ids,
            query=_file_query(path, mode),
            content=content,
            content_type="application/octet-stream",
        )
        body = res.content
        if not 200 <= res.status_code < 300:
            raise _response_error("file.upload", res, body, ids)
        envelope = _envelope(
            ops.Request(
                action="file.upload",
                method="PUT",
                path=path,
                statuses=(200,),
                sandbox_id=sandbox_id,
            ),
            res,
            body,
        )
        return models.SandboxFileUploadResult.parse(
            envelope.data, "sandbox file upload result"
        )

    def download(self, sandbox_id: str, path: str) -> bytes:
        ids: dict[str, str | None] = {"sandbox_id": sandbox_id}
        res = self._send(
            "file.download",
            "GET",
            f"{ops.sandbox_path(sandbox_id)}/files",
            ids=ids,
            query={"path": path},
        )
        body = res.content
        if not 200 <= res.status_code < 300:
            raise _response_error("file.download", res, body, ids)
        return _check_download(res, body, sandbox_id)

    @contextlib.contextmanager
    def stream(
        self,
        action: SandboxAction,
        path: str,
        query: dict[str, str],
        *,
        sandbox_id: str,
        process_id: str | None = None,
    ) -> typing.Iterator[typing.Iterator[models.SandboxOutputChunk]]:
        ids: dict[str, str | None] = {
            "sandbox_id": sandbox_id,
            "process_id": process_id,
        }
        res = self._send(
            action,
            "GET",
            path,
            ids=ids,
            query=query,
            timeout=_STREAM_TIMEOUT,
            stream=True,
        )
        try:
            if not 200 <= res.status_code < 300:
                raise _stream_error_sync(action, res, ids)

            def chunks() -> typing.Iterator[models.SandboxOutputChunk]:
                request_id = _request_id(res)
                try:
                    for line in res.iter_lines():
                        chunk = _frame(
                            line, action, res.status_code, request_id, ids
                        )
                        if chunk is not None:
                            yield chunk
                except httpx.RequestError as err:
                    raise _transport_failure(action, ids) from err

            yield chunks()
        finally:
            res.close()
