from __future__ import annotations

import dataclasses
import datetime
import hashlib
import hmac
import http
import threading
import time
import typing
import urllib.parse

import httpx

from inngest._internal import (
    async_lib,
    config_lib,
    const,
    errors,
    server_lib,
    transforms,
    types,
)


class AuthenticatedHTTPClient:
    """
    HTTP client that:
    - Is thread-safe
    - Works in both async and sync contexts
    - Handles auth (opt in)
    - Handles branch environments
    """

    def __init__(
        self,
        *,
        env: typing.Optional[str],
        request_timeout: int | datetime.timedelta | None = None,
        signing_key: typing.Optional[str],
        signing_key_fallback: typing.Optional[str],
    ):
        self._http_client = ThreadAwareAsyncHTTPClient().initialize()
        self._http_client_sync = httpx.Client()

        # This is probably leaking an implementation detail, and maybe we should
        # eventually remove it. In the meantime, it simplifies initial
        # HTTPClient implementation
        self.build_httpx_request = self._http_client_sync.build_request

        self._env = env
        self._signing_key = signing_key
        self._signing_key_fallback = signing_key_fallback

        if isinstance(request_timeout, int):
            self._default_timeout = request_timeout / 1000  # convert ms to s
        elif isinstance(request_timeout, datetime.timedelta):
            self._default_timeout = request_timeout.total_seconds()
        else:
            self._default_timeout = 30.0

    async def get(
        self,
        url: str,
        *,
        auth: bool = False,
        headers: dict[str, str] | None = None,
    ) -> types.MaybeError[httpx.Response]:
        """
        Perform an async HTTP GET request.

        Args:
        ----
            url: Request URL
            auth: Include the Authorization header. Never set to True if the request is not to an Inngest server
            headers: Additional request headers
        """

        req = self.build_httpx_request(
            "GET",
            url,
            headers={
                # Default headers
                **create_headers(
                    env=self._env,
                    framework=None,
                    server_kind=None,
                ),
                # Additional headers or overrides
                **(headers or {}),
            },
        )

        if auth:
            res = await fetch_with_auth_fallback(
                self._http_client,
                self._http_client_sync,
                req,
                signing_key=self._signing_key,
                signing_key_fallback=self._signing_key_fallback,
            )
        else:
            res = await fetch_with_thready_safety(
                self._http_client,
                self._http_client_sync,
                req,
            )
        if isinstance(res, Exception):
            return res

        if res.status_code >= 400:
            return Exception(f"HTTP error: {res.status_code} {res.text}")

        return res

    def get_sync(
        self,
        url: str,
        *,
        auth: bool = False,
        headers: dict[str, str] | None = None,
    ) -> types.MaybeError[httpx.Response]:
        """
        Perform a sync HTTP GET request.

        Args:
        ----
            url: Request URL
            auth: Include the Authorization header. Never set to True if the request is not to an Inngest server
            headers: Additional request headers
        """

        req = self.build_httpx_request(
            "GET",
            url,
            headers={
                # Default headers
                **create_headers(
                    env=self._env,
                    framework=None,
                    server_kind=None,
                ),
                # Additional headers or overrides
                **(headers or {}),
            },
        )

        if auth:
            res = fetch_with_auth_fallback_sync(
                self._http_client_sync,
                req,
                signing_key=self._signing_key,
                signing_key_fallback=self._signing_key_fallback,
            )
        else:
            res = self._http_client_sync.send(req)

        if isinstance(res, Exception):
            return res

        if res.status_code >= 400:
            return Exception(f"HTTP error: {res.status_code} {res.text}")

        return res

    async def post(
        self, url: str, body: object
    ) -> types.MaybeError[httpx.Response]:
        """
        Perform an asynchronous HTTP POST request. Handles authn

        Args:
        ----
            url: The pathname to the endpoint, including query string
            body: The body of the request

        Returns:
        -------
            A httpx.Response object
        """
        req = self.build_httpx_request(
            "POST",
            url,
            headers=create_headers(
                env=self._env,
                framework=None,
                server_kind=None,
            ),
            json=body,
            timeout=self._default_timeout,
        )

        res = await fetch_with_auth_fallback(
            self._http_client,
            self._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        if res.status_code >= 400:
            return Exception(f"HTTP error: {res.status_code} {res.text}")

        return res

    def post_sync(
        self, url: str, body: object
    ) -> types.MaybeError[httpx.Response]:
        """
        Perform a synchronous HTTP POST request. Handles authn

        Args:
        ----
            url: The pathname to the endpoint, including query string
            body: The body of the request

        Returns:
        -------
            A httpx.Response object
        """
        req = self.build_httpx_request(
            "POST",
            url,
            headers=create_headers(
                env=self._env,
                framework=None,
                server_kind=None,
            ),
            json=body,
            timeout=self._default_timeout,
        )

        res = fetch_with_auth_fallback_sync(
            self._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        if res.status_code >= 400:
            return Exception(f"HTTP error: {res.status_code} {res.text}")

        return res


class ThreadAwareAsyncHTTPClient(httpx.AsyncClient):
    """
    Thin wrapper around httpx.AsyncClient. It keeps track of the thread it was
    created in, which is critical since asyncio is not thread safe: calling an
    async method in a different thread will raise an exception
    """

    _creation_thread_id: typing.Optional[int] = None

    def is_same_thread(self) -> bool:
        if self._creation_thread_id is None:
            raise Exception("did not initialize ThreadAwareAsyncHTTPClient")

        current_thread_id = threading.get_ident()
        return self._creation_thread_id == current_thread_id

    def initialize(self) -> ThreadAwareAsyncHTTPClient:
        self._creation_thread_id = threading.get_ident()
        return self


def create_headers(
    *,
    env: typing.Optional[str],
    framework: typing.Optional[server_lib.Framework],
    server_kind: typing.Optional[server_lib.ServerKind],
) -> dict[str, str]:
    """
    Create standard headers that should exist on every possible outgoing
    request.
    """

    headers = {
        server_lib.HeaderKey.CONTENT_TYPE.value: "application/json",
        server_lib.HeaderKey.SDK.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
        server_lib.HeaderKey.REQUEST_VERSION.value: server_lib.PREFERRED_EXECUTION_VERSION,
        server_lib.HeaderKey.USER_AGENT.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
    }

    if env is not None:
        headers[server_lib.HeaderKey.ENV.value] = env
    if framework is not None:
        headers[server_lib.HeaderKey.FRAMEWORK.value] = framework.value
    if server_kind is not None:
        headers[server_lib.HeaderKey.EXPECTED_SERVER_KIND.value] = (
            server_kind.value
        )

    return headers


def create_serve_url(
    *,
    public_path: typing.Optional[str],
    request_url: str,
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> str:
    """
    Create the serve URL, which is the URL that the Executor will use to reach
    the SDK.

    Args:
    ----
        public_path: User-specified override for the public path.
        request_url: The URL that the Executor is using to reach the SDK.
        serve_origin: User-specified override for the serve origin.
        serve_path: User-specified override for the serve path.
    """

    # User can also specify these via env vars. The env vars take precedence.
    serve_origin = config_lib.get_serve_origin(serve_origin)
    serve_path = config_lib.get_serve_path(serve_path)

    parsed_url = urllib.parse.urlparse(request_url)
    new_scheme = parsed_url.scheme
    new_netloc = parsed_url.netloc
    new_path = parsed_url.path

    if serve_origin is not None:
        has_scheme = "://" in serve_origin
        if has_scheme:
            parsed_origin = urllib.parse.urlparse(serve_origin)
            new_scheme = parsed_origin.scheme or new_scheme
            new_netloc = parsed_origin.netloc or new_netloc
        else:
            new_scheme = "https"
            new_netloc = serve_origin

    if serve_path is not None:
        new_path = serve_path

    # public_path takes precedence over serve_path because it allows users to
    # decouple their publicly-reachable path (that the Inngest server sends
    # requests to) and the path that our SDK is hosted on. This is useful when
    # the SDK is behind a proxy that rewrites the path
    if public_path is not None:
        new_path = public_path

    return urllib.parse.urlunparse(
        (new_scheme, new_netloc, new_path, "", "", "")
    )


async def fetch_with_auth_fallback(
    client: ThreadAwareAsyncHTTPClient,
    client_sync: httpx.Client,
    request: httpx.Request,
    *,
    signing_key: typing.Optional[str],
    signing_key_fallback: typing.Optional[str],
) -> types.MaybeError[httpx.Response]:
    """
    Send an HTTP request with the given signing key. If the response is a 401 or
    403, then try again with the fallback signing key
    """

    if signing_key is not None:
        request.headers[server_lib.HeaderKey.AUTHORIZATION.value] = (
            f"Bearer {transforms.hash_signing_key(signing_key)}"
        )

    try:
        res = await fetch_with_thready_safety(
            client,
            client_sync,
            request,
        )
        if (
            res.status_code
            in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)
            and signing_key_fallback is not None
        ):
            # Try again with the signing key fallback
            request.headers[server_lib.HeaderKey.AUTHORIZATION.value] = (
                f"Bearer {transforms.hash_signing_key(signing_key_fallback)}"
            )

            res = await fetch_with_thready_safety(
                client,
                client_sync,
                request,
            )

        return res
    except Exception as err:
        new_err = Exception(f"Failed request to {request.url}: {err}")
        new_err.__cause__ = err
        return new_err


def fetch_with_auth_fallback_sync(
    client: httpx.Client,
    request: httpx.Request,
    *,
    signing_key: typing.Optional[str],
    signing_key_fallback: typing.Optional[str],
) -> types.MaybeError[httpx.Response]:
    """
    Send an HTTP request with the given signing key. If the response is a 401 or
    403, then try again with the fallback signing key. Returns an error when
    receiving a non-OK response
    """

    if signing_key is not None:
        request.headers[server_lib.HeaderKey.AUTHORIZATION.value] = (
            f"Bearer {transforms.hash_signing_key(signing_key)}"
        )

    try:
        res = client.send(request)
        if (
            res.status_code
            in (http.HTTPStatus.FORBIDDEN, http.HTTPStatus.UNAUTHORIZED)
            and signing_key_fallback is not None
        ):
            # Try again with the signing key fallback
            request.headers[server_lib.HeaderKey.AUTHORIZATION.value] = (
                f"Bearer {transforms.hash_signing_key(signing_key_fallback)}"
            )
            res = client.send(request)
        return res
    except Exception as err:
        new_err = Exception(f"Failed request to {request.url}: {err}")
        new_err.__cause__ = err
        return new_err


def normalize_headers(
    headers: typing.Union[dict[str, str], dict[str, list[str]]],
) -> dict[str, str]:
    """
    Ensure that known headers are in the correct casing.
    """

    new_headers = {}

    for k, v in headers.items():
        k = k.lower()

        if isinstance(v, list):
            new_headers[k] = v[0]
        else:
            new_headers[k] = v

    return new_headers


def parse_url(url: str, mode: server_lib.ServerKind) -> types.MaybeError[str]:
    if "." not in url and ":" not in url.strip("http://").strip("https://"):
        return Exception("invalid URL: no domain or port")

    if url.startswith("http") is False:
        if mode is server_lib.ServerKind.CLOUD:
            url = f"https://{url}"
        else:
            url = f"http://{url}"

    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == "":
            return Exception("invalid URL")

        return parsed.geturl()
    except Exception as err:
        return err


async def fetch_with_thready_safety(
    client: ThreadAwareAsyncHTTPClient,
    client_sync: httpx.Client,
    request: httpx.Request,
) -> httpx.Response:
    """
    Safely handles the situation where the async HTTP client is called in a
    different thread.
    """

    if client.is_same_thread() is True:
        # Python freaks out if you call httpx.AsyncClient's methods in multiple
        # threads. So we'll only use it if we're in the same thread as its first
        # method call
        return await client.send(request)

    loop = async_lib.get_event_loop()
    if loop is None:
        return client_sync.send(request)

    return await loop.run_in_executor(
        None,
        lambda: client_sync.send(request),
    )


def sign_request(
    body: bytes,
    signing_key: str,
    unix_ms: typing.Optional[int] = None,
) -> types.MaybeError[str]:
    """
    Sign an HTTP request in the same way an Inngest server would. This is only
    needed for tests that mimic Inngest server behavior.
    """

    if unix_ms is None:
        unix_ms = round(time.time())

    canonicalized = transforms.canonicalize(body)
    if isinstance(canonicalized, Exception):
        raise canonicalized

    mac = hmac.new(
        transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
        canonicalized,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    sig = mac.hexdigest()

    # Order matters since Inngest Cloud compares strings
    return f"t={unix_ms}&s={sig}"


def sign_response(
    body: bytes,
    signing_key: str,
    unix_ms: typing.Optional[int] = None,
) -> types.MaybeError[str]:
    """
    Sign an HTTP response.
    """

    if unix_ms is None:
        unix_ms = round(time.time())

    mac = hmac.new(
        transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
        body,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    sig = mac.hexdigest()

    # Order matters since Inngest Cloud compares strings
    return f"t={unix_ms}&s={sig}"


def _validate_sig(
    *,
    body: bytes,
    headers: dict[str, str],
    mode: server_lib.ServerKind,
    signing_key: typing.Optional[str],
) -> types.MaybeError[typing.Optional[str]]:
    if mode == server_lib.ServerKind.DEV_SERVER:
        return None

    timestamp = None
    signature = None
    sig_header = headers.get(server_lib.HeaderKey.SIGNATURE.value)
    if sig_header is None:
        return errors.HeaderMissingError(
            f"cannot validate signature in production mode without a {server_lib.HeaderKey.SIGNATURE.value} header"
        )
    else:
        parsed = urllib.parse.parse_qs(sig_header)
        if "t" in parsed:
            timestamp = int(parsed["t"][0])
        if "s" in parsed:
            signature = parsed["s"][0]

    if signing_key is None:
        return errors.SigningKeyMissingError(
            "cannot validate signature in production mode without a signing key"
        )

    if signature is None:
        return Exception(
            f"{server_lib.HeaderKey.SIGNATURE.value} header is malformed"
        )

    mac = hmac.new(
        transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
        body,
        hashlib.sha256,
    )

    if timestamp:
        mac.update(str(timestamp).encode("utf-8"))

    if not hmac.compare_digest(signature, mac.hexdigest()):
        return errors.SigVerificationFailedError()

    return signing_key


def validate_request_sig(
    *,
    body: bytes,
    headers: dict[str, str],
    mode: server_lib.ServerKind,
    signing_key: typing.Optional[str],
    signing_key_fallback: typing.Optional[str],
) -> types.MaybeError[typing.Optional[str]]:
    """
    Validate the request signature. Falls back to the fallback signing key if
    signature validation fails with the primary signing key.

    Args:
    ----
        body: Request body.
        headers: Request headers.
        mode: Server mode.
        signing_key: Primary signing key.
        signing_key_fallback: Fallback signing key.
    """

    canonicalized = transforms.canonicalize(body)
    if isinstance(canonicalized, Exception):
        return canonicalized

    err = _validate_sig(
        body=canonicalized,
        headers=headers,
        mode=mode,
        signing_key=signing_key,
    )
    if isinstance(err, Exception) and signing_key_fallback is not None:
        # If the signature validation failed but there's a "fallback"
        # signing key, attempt to validate the signature with the fallback
        # key
        err = _validate_sig(
            body=canonicalized,
            headers=headers,
            mode=mode,
            signing_key=signing_key_fallback,
        )

    return err


def validate_response_sig(
    *,
    body: bytes,
    headers: dict[str, str],
    mode: server_lib.ServerKind,
    signing_key: str,
) -> types.MaybeError[typing.Optional[str]]:
    """
    Validate an HTTP response signature in the same way an Inngest server would.
    This is only needed for tests that mimic Inngest server behavior.

    Args:
    ----
        body: Request body.
        headers: Request headers.
        mode: Server mode.
        signing_key: Primary signing key.
    """

    return _validate_sig(
        body=body,
        headers=headers,
        mode=mode,
        signing_key=signing_key,
    )


@dataclasses.dataclass
class ServerTiming:
    def __init__(self, name: str) -> None:
        self._name = name
        self._start_counter: float | None = None
        self._end_counter: float | None = None

    def __enter__(self) -> ServerTiming:
        self._start()
        return self

    def __exit__(self, *args: object) -> None:
        self._end()

    def _start(self) -> None:
        if self._start_counter is not None:
            return

        self._start_counter = time.perf_counter()

    def _end(self) -> None:
        if self._end_counter is not None:
            return

        self._end_counter = time.perf_counter()

    def to_header(self) -> str:
        if self._start_counter is None or self._end_counter is None:
            return ""

        dur = int((self._end_counter - self._start_counter) * 1000)
        if dur == 0:
            return ""

        return f"{self._name};dur={dur}"


class ServerTimings:
    def __init__(self) -> None:
        # CommHandler method. This should include basically everything but
        # general HTTP framework stuff (e.g. everything besides FastAPI stuff)
        self.comm_handler = ServerTiming("comm_handler")

        # Calling the Inngest function
        self.function = ServerTiming("function")

        self.mw_transform_input = ServerTiming("mw.transform_input")
        self.mw_transform_output = ServerTiming("mw.transform_output")

        # When the SDK sends an outgoing request to fetch the events and steps.
        # This happens when the incoming SDK request would be too large
        self.use_api = ServerTiming("use_api")

    def to_header(self) -> str:
        """
        Convert the server timings to the Server-Timing header value
        """

        timings = [
            self.comm_handler,
            self.function,
            self.mw_transform_input,
            self.mw_transform_output,
            self.use_api,
        ]

        # Sort by start time
        timings = sorted(
            timings,
            key=lambda x: x._start_counter or 0,
        )

        values: list[str] = [timing.to_header() for timing in timings]

        # Remove empty values
        values = [v for v in values if v != ""]

        return ", ".join(values)
