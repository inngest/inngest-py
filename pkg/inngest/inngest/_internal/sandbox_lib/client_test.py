"""
Direct sandbox client behavior against a fake REST API. Each lifecycle test
runs against both the async and sync clients.
"""

from __future__ import annotations

import asyncio
import datetime
import gc
import http.server
import inspect
import io
import signal
import threading
import typing

import httpx
import pytest

import inngest
from inngest.experimental.sandbox import (
    SandboxError,
    SandboxErrorCode,
    SandboxValidationError,
    image,
)

from . import ops
from .fake_api_test import FALLBACK_KEY, SIGNING_KEY, FakeAPI, hashed


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ops, "POLL_INTERVAL_SECONDS", 0.001)


async def resolve(value: typing.Any) -> typing.Any:
    if inspect.isawaitable(value):
        return await value
    return value


def sandboxes(fake: FakeAPI, is_sync: bool, **kwargs: typing.Any) -> typing.Any:
    client = fake.client(**kwargs)
    return client.sandboxes_sync if is_sync else client.sandboxes


@pytest.mark.parametrize("is_sync", [False, True])
def test_lifecycle(is_sync: bool) -> None:
    fake = FakeAPI()
    api = sandboxes(fake, is_sync)

    async def check() -> None:
        sb = await resolve(api.create(name="job-1", vcpu=1, memory_mb=1024))
        # Create returned STARTING; the SDK polled until RUNNING.
        assert sb.status == "RUNNING"
        assert fake.count("GET /v2/sandboxes/{id}") == 1
        assert fake.last("POST /v2/sandboxes").json == {
            "name": "job-1",
            "vcpu": 1,
            "memoryMb": 1024,
        }

        # A string runs through the shell with the default timeout.
        res = await resolve(sb.commands.run("echo hi"))
        assert res.stdout == "/bin/sh -c echo hi|30000ms"
        assert res.stderr == "warn"
        assert res.exit_code == 3
        assert res.output.truncated is False

        # An argv runs as given, with its options.
        res = await resolve(
            sb.commands.run(
                ["python", "-V"],
                cwd="/app",
                environment={"A": "1"},
                timeout=datetime.timedelta(minutes=5),
            )
        )
        assert res.stdout == "python -V|300000ms"
        assert fake.last("POST /v2/sandboxes/{id}/exec").json == {
            "command": ["python", "-V"],
            "environment": {"A": "1"},
            "cwd": "/app",
            "timeout": "300000ms",
        }

        # The API omits a zero exit code and empty output.
        fake.exec_stdout, fake.exec_stderr, fake.exec_exit_code = b"", b"", 0
        res = await resolve(sb.commands.run("true"))
        assert (res.stdout, res.stderr, res.exit_code) == ("", "", 0)

        proc = await resolve(sb.processes.start(["sleep", "100"]))
        assert (proc.state, proc.pid, proc.sandbox_id) == ("RUNNING", 42, sb.id)
        assert (await resolve(sb.processes.get(proc.id))).id == proc.id
        listed = await resolve(sb.processes.list())
        assert [p.id for p in listed.items] == [proc.id]

        await resolve(proc.signal(signal.SIGTERM))
        assert fake.last(
            "POST /v2/sandboxes/{id}/processes/{id}/signals"
        ).json == {"signal": 15, "includeChildren": True}

        done = await resolve(proc.wait())
        assert (done.state, done.exit_code, done.done) == ("EXITED", 0, True)
        assert fake.last(
            "POST /v2/sandboxes/{id}/processes/{id}/wait"
        ).query == {"timeout": "30000ms"}

        output = await resolve(proc.get_output(tail_bytes=10))
        assert [c.data for c in output.chunks] == [b"hello"]
        assert output.chunks[0].at is not None

        uploaded = await resolve(
            sb.files.upload("/app/main.py", "print('é')", mode=0o640)
        )
        assert uploaded.bytes_written == len("print('é')".encode())
        assert fake.last("PUT /v2/sandboxes/{id}/files").query == {
            "path": "/app/main.py",
            "mode": "0640",
        }
        assert (
            await resolve(sb.files.download("/app/main.py"))
            == "print('é')".encode()
        )

        paused = await resolve(sb.pause())
        assert paused.status == "PAUSED"
        resumed = await resolve(paused.resume())
        assert resumed.status == "RUNNING"

        snapshot = await resolve(sb.snapshot(name="deps"))
        assert (snapshot.status, snapshot.name) == ("READY", "deps")
        assert snapshot.info.stored_bytes == 1024
        assert fake.last("POST /v2/sandboxes/{id}/snapshots").json == {
            "name": "deps"
        }
        found = await resolve(api.snapshots.list(name="deps"))
        assert [s.id for s in found.items] == [snapshot.id]

        clone = await resolve(snapshot.clone(name="job-1-clone"))
        assert clone.status == "RUNNING"
        assert fake.last("POST /v2/sandboxes").json == {
            "name": "job-1-clone",
            "snapshotId": snapshot.id,
        }

        destroyed = await resolve(sb.destroy())
        assert destroyed.status == "TERMINATING"
        assert destroyed.sandbox is not None
        assert await resolve(api.get(sb.id)) is None

    asyncio.run(check())


def test_unnamed_snapshot_sends_no_body() -> None:
    fake = FakeAPI()
    sb = fake.client().sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024)
    sb.snapshot()
    assert fake.last("POST /v2/sandboxes/{id}/snapshots").request.content == b""


def test_context_managers_destroy() -> None:
    fake = FakeAPI()
    client = fake.client()

    with client.sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024):
        pass
    assert fake.count("DELETE /v2/sandboxes/{id}") == 1

    async def check() -> None:
        async with client.sandboxes.create(name="b", vcpu=1, memory_mb=1024):
            pass

    asyncio.run(check())
    assert fake.count("DELETE /v2/sandboxes/{id}") == 2
    assert fake.sandboxes == {}


def test_create_without_wait_does_not_poll() -> None:
    fake = FakeAPI()
    sb = fake.client().sandboxes_sync.create(
        name="a", vcpu=1, memory_mb=1024, wait=False
    )
    assert sb.status == "STARTING"
    assert fake.count("GET /v2/sandboxes/{id}") == 0


def test_wait_polls_through_availability_errors() -> None:
    fake = FakeAPI()
    fake.fail["GET /v2/sandboxes/{id}"] = (503, "compute_unavailable")
    sb = fake.client().sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024)
    assert sb.status == "RUNNING"
    assert fake.count("GET /v2/sandboxes/{id}") == 2


def test_wait_stops_on_terminal_state() -> None:
    fake = FakeAPI()
    sb = fake.client().sandboxes_sync.create(
        name="a", vcpu=1, memory_mb=1024, wait=False
    )
    fake.next_status[sb.id] = "FAILED"
    with pytest.raises(SandboxError) as caught:
        sb.wait_until_running(timeout=1000)
    assert caught.value.code == SandboxErrorCode.START_FAILED
    assert caught.value.retryable is False


@pytest.mark.parametrize("is_sync", [False, True])
def test_create_destroys_a_new_sandbox_that_fails_to_start(
    is_sync: bool,
) -> None:
    fake = FakeAPI()
    existing = fake.add_sandbox(status="PAUSED")
    api = sandboxes(fake, is_sync)

    real_create = fake._create

    def create_failing(body: dict[str, typing.Any]) -> httpx.Response:
        response = real_create(body)
        for sandbox_id in fake.next_status:
            fake.next_status[sandbox_id] = "FAILED"
        return response

    fake._create = create_failing  # type: ignore[method-assign]

    async def check() -> None:
        with pytest.raises(SandboxError) as caught:
            await resolve(api.create(name="new", vcpu=1, memory_mb=1024))
        assert caught.value.code == SandboxErrorCode.START_FAILED

        # Create returned an existing sandbox, which isn't ours to destroy.
        with pytest.raises(SandboxError) as caught:
            await resolve(api.create(name="existing", vcpu=1, memory_mb=1024))
        assert caught.value.code == SandboxErrorCode.START_FAILED

    asyncio.run(check())
    assert fake.count("DELETE /v2/sandboxes/{id}") == 1
    assert list(fake.sandboxes) == [existing["id"]]


@pytest.mark.parametrize("is_sync", [False, True])
def test_context_manager_keeps_the_block_error(is_sync: bool) -> None:
    fake = FakeAPI()
    client = fake.client()
    destroy_fails = ("DELETE /v2/sandboxes/{id}", (500, "internal_error"))

    async def check() -> None:
        async with client.sandboxes.create(name="a", vcpu=1, memory_mb=1024):
            fake.fail[destroy_fails[0]] = destroy_fails[1]
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        if is_sync:
            with client.sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024):
                fake.fail[destroy_fails[0]] = destroy_fails[1]
                raise ValueError("boom")
        else:
            asyncio.run(check())
    assert fake.count("DELETE /v2/sandboxes/{id}") == 1

    # Without a block error, the destroy error is raised.
    with pytest.raises(SandboxError):
        with client.sandboxes_sync.create(name="b", vcpu=1, memory_mb=1024):
            fake.fail[destroy_fails[0]] = destroy_fails[1]


@pytest.mark.parametrize("is_sync", [False, True])
def test_create_with_image(is_sync: bool) -> None:
    fake = FakeAPI()
    api = sandboxes(fake, is_sync)

    async def check() -> None:
        sb = await resolve(
            api.create(
                name="a",
                vcpu=1,
                memory_mb=1024,
                image=image.custom("my-image:v1"),
            )
        )
        assert fake.last("POST /v2/sandboxes").json["image"] == "my-image:v1"
        assert sb.image_ref == "my-image:v1"
        assert sb.image_digest == "sha256:" + "d" * 64

        # Without an image, the API picks the default and pins no digest.
        sb = await resolve(api.create(name="b", vcpu=1, memory_mb=1024))
        assert "image" not in fake.last("POST /v2/sandboxes").json
        assert sb.image_digest is None

        with pytest.raises(SandboxError) as caught:
            await resolve(
                api.create(name="c", vcpu=1, memory_mb=1024, image="missing")
            )
        assert caught.value.code == SandboxErrorCode.IMAGE_NOT_FOUND
        assert caught.value.retryable is False

    asyncio.run(check())


def test_lists_parse_omitted_zero_values() -> None:
    fake = FakeAPI()
    result = fake.client().sandboxes_sync.list()
    assert result.items == []
    assert result.page.has_more is False
    assert result.page.cursor is None
    assert fake.last("GET /v2/sandboxes").query == {"limit": "50"}


@pytest.mark.parametrize(
    ("key", "status", "code", "call", "retryable", "ambiguous"),
    [
        (
            "POST /v2/sandboxes/{id}/exec",
            503,
            "compute_unavailable",
            "exec",
            True,
            False,
        ),
        (
            "POST /v2/sandboxes/{id}/exec",
            429,
            "sandbox_concurrency_limit_exceeded",
            "exec",
            True,
            False,
        ),
        (
            "POST /v2/sandboxes/{id}/exec",
            409,
            "operation_ambiguous",
            "exec",
            False,
            True,
        ),
        (
            "POST /v2/sandboxes/{id}/exec",
            504,
            "sandbox_exec_timed_out",
            "exec",
            False,
            True,
        ),
        (
            "POST /v2/sandboxes/{id}/exec",
            413,
            "sandbox_exec_output_too_large",
            "exec",
            False,
            True,
        ),
        (
            "POST /v2/sandboxes/{id}/exec",
            409,
            "invalid_request",
            "exec",
            False,
            False,
        ),
        ("GET /v2/sandboxes/{id}", 429, "rate_limited", "get", True, False),
        ("GET /v2/sandboxes/{id}", 403, "access_denied", "get", False, False),
    ],
)
def test_error_classification(
    key: str,
    status: int,
    code: str,
    call: str,
    retryable: bool,
    ambiguous: bool,
) -> None:
    fake = FakeAPI()
    sb = fake.client().sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024)
    fake.fail[key] = (status, code)
    with pytest.raises(SandboxError) as caught:
        if call == "exec":
            sb.commands.run("x")
        else:
            fake.client().sandboxes_sync.get(sb.id)
    err = caught.value
    assert (err.code, err.status) == (code, status)
    assert (err.retryable, err.ambiguous) == (retryable, ambiguous)
    assert err.sandbox_id == sb.id
    assert err.request_id == "req-1"


@pytest.mark.parametrize(
    ("key", "call", "error", "code", "retryable", "ambiguous"),
    [
        # The response was lost, but repeating is safe.
        (
            "GET /v2/sandboxes/{id}",
            "get",
            httpx.ReadError,
            "compute_unavailable",
            True,
            False,
        ),
        (
            "DELETE /v2/sandboxes/{id}",
            "destroy",
            httpx.ReadError,
            "compute_unavailable",
            True,
            False,
        ),
        # The command may have run.
        (
            "POST /v2/sandboxes/{id}/exec",
            "exec",
            httpx.ReadError,
            "operation_ambiguous",
            False,
            True,
        ),
        (
            "POST /v2/sandboxes/{id}/processes",
            "start",
            httpx.RemoteProtocolError,
            "operation_ambiguous",
            False,
            True,
        ),
        # The request was never sent, so nothing ran.
        (
            "POST /v2/sandboxes/{id}/exec",
            "exec",
            httpx.ConnectError,
            "compute_unavailable",
            True,
            False,
        ),
        (
            "POST /v2/sandboxes/{id}/processes",
            "start",
            httpx.ConnectTimeout,
            "compute_unavailable",
            True,
            False,
        ),
    ],
)
def test_transport_failure_classification(
    key: str,
    call: str,
    error: type[httpx.TransportError],
    code: str,
    retryable: bool,
    ambiguous: bool,
) -> None:
    fake = FakeAPI()
    api = fake.client().sandboxes_sync
    sb = api.create(name="a", vcpu=1, memory_mb=1024)
    fake.raise_transport_error[key] = error
    with pytest.raises(SandboxError) as caught:
        if call == "get":
            api.get(sb.id)
        elif call == "destroy":
            sb.destroy()
        elif call == "exec":
            sb.commands.run("x")
        else:
            sb.processes.start("x")
    err = caught.value
    assert (err.code, err.retryable, err.ambiguous) == (
        code,
        retryable,
        ambiguous,
    )
    assert err.status is None


@pytest.mark.parametrize(
    ("status", "call", "retryable", "ambiguous"),
    [
        # A gateway error is a lost response: repeat what's safe to repeat.
        (502, "list", True, False),
        (504, "list", True, False),
        (502, "exec", False, True),
        (504, "exec", False, True),
        (500, "list", False, False),
    ],
)
def test_non_json_error_response(
    status: int, call: str, retryable: bool, ambiguous: bool
) -> None:
    fake = FakeAPI()
    api = fake.client().sandboxes_sync
    sb = api.create(name="a", vcpu=1, memory_mb=1024)

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=b"<html>bad gateway</html>")

    fake.transport.handler = broken
    with pytest.raises(SandboxError) as caught:
        if call == "list":
            api.list()
        else:
            sb.commands.run("x")
    assert caught.value.code == "internal_error"
    assert caught.value.status == status
    assert (caught.value.retryable, caught.value.ambiguous) == (
        retryable,
        ambiguous,
    )


@pytest.mark.parametrize("status", [401, 403])
def test_signing_key_hash_and_fallback(status: int) -> None:
    fake = FakeAPI()
    client = fake.client()
    client._signing_key_fallback = FALLBACK_KEY
    fake.reject_auth = hashed(SIGNING_KEY)
    fake.reject_auth_status = status

    client.sandboxes_sync.list()
    assert [c.auth for c in fake.calls] == [
        hashed(SIGNING_KEY),
        hashed(FALLBACK_KEY),
    ]


def test_requires_signing_key_in_cloud_mode() -> None:
    fake = FakeAPI()
    api = fake.client(signing_key=None).sandboxes_sync
    with pytest.raises(SandboxValidationError, match="signing key is required"):
        api.list()
    assert fake.calls == []


def test_dev_server_needs_no_key() -> None:
    fake = FakeAPI()
    fake.client(signing_key=None, is_production=False).sandboxes_sync.list()
    assert fake.calls[0].auth is None


def test_env_header() -> None:
    fake = FakeAPI()
    client = fake.client()
    client._env = "feature-branch"
    client.sandboxes_sync.list()
    assert fake.calls[0].request.headers["x-inngest-env"] == "feature-branch"


@pytest.mark.parametrize("is_sync", [False, True])
def test_streams(is_sync: bool) -> None:
    fake = FakeAPI()
    client = fake.client()

    async def check() -> list[bytes]:
        if is_sync:
            sb = client.sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024)
            with sb.logs.stream(follow=True) as chunks:
                return [c.data for c in chunks]
        asb = await client.sandboxes.create(name="a", vcpu=1, memory_mb=1024)
        async with asb.logs.stream(follow=True) as achunks:
            return [c.data async for c in achunks]

    # Blank lines between frames are skipped.
    assert asyncio.run(check()) == [b"one", b"two"]
    assert fake.last("GET /v2/sandboxes/{id}/logs").query == {"follow": "true"}


def test_stream_error_frame() -> None:
    fake = FakeAPI()
    sb = fake.client().sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024)
    proc = sb.processes.start("x")
    fake.stream_lines = [
        '{"type":"log","stream":"STDERR","data":"b2s=","encoding":"base64"}',
        '{"type":"error","error":{"code":"compute_unavailable","message":"node lost"}}',
    ]
    received: list[bytes] = []
    with pytest.raises(SandboxError) as caught:
        with proc.stream_output() as chunks:
            for chunk in chunks:
                received.append(chunk.data)
    assert received == [b"ok"]
    assert caught.value.code == "compute_unavailable"
    assert caught.value.process_id == proc.id
    assert caught.value.action == "process.stream"


def test_short_download_is_retryable() -> None:
    fake = FakeAPI()
    sb = fake.client().sandboxes_sync.create(name="a", vcpu=1, memory_mb=1024)
    sb.files.upload("/f", b"abc")
    fake.download_content_length = 10
    with pytest.raises(SandboxError) as caught:
        sb.files.download("/f")
    assert caught.value.code == "compute_unavailable"
    assert caught.value.retryable is True


def test_get_validates_ids_before_sending() -> None:
    fake = FakeAPI()
    with pytest.raises(
        SandboxValidationError, match="canonical lowercase UUID"
    ):
        fake.client().sandboxes_sync.get("NOT-A-UUID")
    assert fake.calls == []


def test_async_upload_reads_async_files() -> None:
    class AsyncFile:
        # Like aiofiles: read() is a coroutine and iteration is async.
        async def read(self, size: int = -1) -> bytes:
            raise AssertionError("read() should not be called")

        async def __aiter__(self) -> typing.AsyncIterator[bytes]:
            yield b"line 1\n"
            yield b"line 2\n"

    fake = FakeAPI()

    async def upload() -> None:
        sb = await fake.client().sandboxes.create(
            name="a", vcpu=1, memory_mb=1024
        )
        await sb.files.upload("/f", AsyncFile())

    asyncio.run(upload())
    assert fake.files["/f"] == b"line 1\nline 2\n"


def test_async_upload_reads_sync_files_in_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from . import transport

    monkeypatch.setattr(transport, "_UPLOAD_CHUNK_BYTES", 4)
    reads: list[int | None] = []

    class File(io.BytesIO):
        def read(self, size: int | None = -1, /) -> bytes:
            reads.append(size)
            return super().read(size)

    fake = FakeAPI()

    async def upload() -> None:
        sb = await fake.client().sandboxes.create(
            name="a", vcpu=1, memory_mb=1024
        )
        await sb.files.upload("/f", File(b"0123456789"))

    asyncio.run(upload())
    assert fake.files["/f"] == b"0123456789"
    # Three chunks, then the empty read that ends the file.
    assert reads == [4, 4, 4, 4]


def test_async_client_does_not_keep_closed_loops() -> None:
    # Over real sockets, an HTTP client references its event loop. Async
    # functions served by a sync framework run each request in a new loop.
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b'{"page":{"limit":50},"metadata":{"fetchedAt":"x"}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = inngest.Inngest(
            app_id="sandbox-test",
            api_base_url=f"http://127.0.0.1:{server.server_address[1]}",
            is_production=False,
        )
        for _ in range(3):
            asyncio.run(client.sandboxes.list())
        gc.collect()
        assert len(client.sandboxes._transport._clients) == 1
    finally:
        server.shutdown()
        server.server_close()
