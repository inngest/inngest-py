"""
Durable sandbox steps, driven through the SDK's request handler with crafted
step memos, the way the Executor calls a function.
"""

from __future__ import annotations

import asyncio
import json
import typing

import pytest

import inngest
from inngest.experimental.sandbox import (
    SandboxError,
    SandboxValidationError,
    image,
)

from .. import comm_lib, net, server_lib, transforms
from . import ops
from .durable_common import SDK_ORIGIN
from .fake_api_test import SIGNING_KEY, FakeAPI

RUN_ID: typing.Final = "01JRUNID"


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ops, "POLL_INTERVAL_SECONDS", 0.001)


def hid(step_id: str) -> str:
    return transforms.hash_step_id(step_id)


class Harness:
    def __init__(self) -> None:
        self.fake = FakeAPI()
        self.client = self.fake.client()
        self.memos: dict[str, object] = {}

    def function(
        self,
        async_fn: typing.Callable[[inngest.Context], typing.Awaitable[object]],
        sync_fn: typing.Callable[[inngest.ContextSync], object],
        is_sync: bool,
        retries: int = 3,
    ) -> inngest.Function[typing.Any]:
        return self.client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="start"),
            retries=retries,
        )(sync_fn if is_sync else async_fn)

    def request(
        self,
        fn: inngest.Function[typing.Any],
        *,
        attempt: int = 0,
        max_attempts: int | None = 4,
    ) -> tuple[comm_lib.CommResponse, typing.Any]:
        event = inngest.Event(name="start")
        body = {
            "ctx": {
                "run_id": RUN_ID,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "disable_immediate_execution": False,
                "stack": {"stack": []},
            },
            "event": event.to_dict(),
            "events": [event.to_dict()],
            "steps": self.memos,
            "use_api": False,
        }
        encoded_body = json.dumps(body).encode()
        signature = net.sign_request(encoded_body, SIGNING_KEY)
        assert isinstance(signature, str)
        req = comm_lib.CommRequest(
            body=encoded_body,
            headers={server_lib.HeaderKey.SIGNATURE.value: signature},
            is_connect=False,
            public_path=None,
            query_params={"fnId": fn.id},
            raw_request=None,
            request_url="",
            serve_origin=None,
            serve_path=None,
        )
        handler = comm_lib.CommHandler(
            client=self.client,
            enable_unauthed_sync=None,
            framework=server_lib.Framework.FAST_API,
            functions=[fn],
            streaming=None,
        )

        async def post() -> comm_lib.CommResponse:
            return await handler.post(req)

        try:
            response = (
                asyncio.run(post())
                if fn.is_handler_async
                else handler.post_sync(req)
            )
            encoded = response.body_bytes()
            assert isinstance(encoded, bytes)
            return response, json.loads(encoded)
        finally:
            if handler._thread_pool is not None:
                handler._thread_pool.shutdown()

    def step(
        self, fn: inngest.Function[typing.Any], **kwargs: typing.Any
    ) -> dict[str, typing.Any]:
        """
        Run until the next step, check it's the only one, and memoize it.
        """

        response, body = self.request(fn, **kwargs)
        assert response.status_code == 206, body
        assert len(body) == 1
        op: dict[str, typing.Any] = body[0]
        memo = {k: op[k] for k in ("data", "error") if k in op}
        self.memos[op["id"]] = memo
        return op


@pytest.mark.parametrize("is_sync", [False, True])
def test_steps_run_once_and_replay(is_sync: bool) -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> str:
        sb = await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        res = await sb.commands.run("run", "echo hi")
        return f"{sb.status}:{res.stdout}:{res.exit_code}"

    def sync_fn(ctx: inngest.ContextSync) -> str:
        sb = ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        res = sb.commands.run("run", "echo hi")
        return f"{sb.status}:{res.stdout}:{res.exit_code}"

    fn = h.function(async_fn, sync_fn, is_sync)

    create = h.step(fn)
    assert (create["id"], create["op"]) == (hid("create"), "StepRun")
    assert create["data"]["protocolVersion"] == 1
    assert create["data"]["sandbox"]["kind"] == "inngest/sandbox"
    assert create["data"]["sandbox"]["status"] == "RUNNING"
    [metadata] = create["metadata"]
    assert metadata["kind"] == "inngest.sandbox"
    assert metadata["values"] == {
        "version": 1,
        "action": "create",
        "method": "create",
        "sandbox_name": "job",
        "sandbox_id": create["data"]["sandbox"]["id"],
    }
    assert h.fake.keys() == ["POST /v2/sandboxes", "GET /v2/sandboxes/{id}"]

    run = h.step(fn)
    assert run["id"] == hid("run")
    assert run["data"]["result"]["encoding"] == "base64"
    assert run["metadata"][0]["values"]["command_display"] == "echo hi"
    assert run["metadata"][0]["values"]["exit_code"] == 3
    # The replayed create made no request.
    assert h.fake.count("POST /v2/sandboxes") == 1

    calls = len(h.fake.calls)
    response, output = h.request(fn)
    assert response.status_code == 200
    assert output == "RUNNING:/bin/sh -c echo hi|30000ms:3"
    assert len(h.fake.calls) == calls


@pytest.mark.parametrize("is_sync", [False, True])
def test_final_error_fails_step_and_replays_as_sandbox_error(
    is_sync: bool,
) -> None:
    h = Harness()
    h.fake.fail["POST /v2/sandboxes"] = (409, "sandbox_name_taken")

    async def async_fn(ctx: inngest.Context) -> object:
        try:
            await ctx.step.sandbox.create(
                "create", name="job", vcpu=1, memory_mb=1024
            )
        except SandboxError as err:
            return [
                err.code,
                err.action,
                err.is_retriable,
                type(err.__cause__).__name__,
            ]
        return None

    def sync_fn(ctx: inngest.ContextSync) -> object:
        try:
            ctx.step.sandbox.create(
                "create", name="job", vcpu=1, memory_mb=1024
            )
        except SandboxError as err:
            return [
                err.code,
                err.action,
                err.is_retriable,
                type(err.__cause__).__name__,
            ]
        return None

    fn = h.function(async_fn, sync_fn, is_sync)

    # Fails now on the first attempt rather than retrying.
    op = h.step(fn, attempt=0)
    assert op["op"] == "StepFailed"
    assert op["error"]["name"] == "SandboxError"
    assert op["error"]["data"]["code"] == "sandbox_name_taken"
    assert op["error"]["data"]["retryable"] is False
    assert op["metadata"][0]["values"]["error_code"] == "sandbox_name_taken"

    # The Executor sends the failure back as a memoized step error.
    h.memos[hid("create")] = {
        "error": {
            k: op["error"][k] for k in ("name", "message", "stack", "data")
        }
    }
    response, output = h.request(fn)
    assert response.status_code == 200
    assert output == ["sandbox_name_taken", "create", False, "StepError"]
    assert h.fake.count("POST /v2/sandboxes") == 1


@pytest.mark.parametrize("is_sync", [False, True])
def test_uncaught_rebuilt_error_does_not_retry_function(is_sync: bool) -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> None:
        await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )

    def sync_fn(ctx: inngest.ContextSync) -> None:
        ctx.step.sandbox.create("create", name="job", vcpu=1, memory_mb=1024)

    fn = h.function(async_fn, sync_fn, is_sync)
    h.memos[hid("create")] = {
        "error": {
            "name": "SandboxError",
            "message": "fake",
            "data": {
                "protocolVersion": 1,
                "action": "create",
                "code": "access_denied",
                "message": "fake access_denied",
                "ambiguous": False,
                "retryable": False,
                "details": [],
            },
        }
    }
    response, body = h.request(fn)
    assert response.status_code == 500
    assert body["name"] == "SandboxError"
    assert response.headers[server_lib.HeaderKey.NO_RETRY.value] == "true"


@pytest.mark.parametrize(
    ("attempt", "op_name"), [(0, "StepError"), (3, "StepFailed")]
)
def test_retryable_error_retries_step(attempt: int, op_name: str) -> None:
    h = Harness()
    h.fake.fail["POST /v2/sandboxes"] = (503, "compute_unavailable")

    async def async_fn(ctx: inngest.Context) -> None:
        await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    op = h.step(fn, attempt=attempt, max_attempts=4)
    assert op["op"] == op_name
    # The last attempt keeps the error fields for the replay.
    assert op["error"]["data"]["code"] == "compute_unavailable"
    assert op["error"]["data"]["retryable"] is True


def test_invalid_input_fails_before_any_step() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> None:
        await ctx.step.sandbox.create(
            "create", name=" job", vcpu=1, memory_mb=1024
        )

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    response, body = h.request(fn)
    assert response.status_code == 500
    assert body["name"] == SandboxValidationError.__name__
    assert response.headers[server_lib.HeaderKey.NO_RETRY.value] == "true"
    assert h.fake.calls == []


def test_destroying_a_missing_sandbox_succeeds() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> str:
        sb = await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        result = await sb.destroy("destroy")
        return result.status

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)
    h.fake.sandboxes.clear()
    op = h.step(fn)
    assert op["op"] == "StepRun"
    assert op["data"]["result"] == {"status": "TERMINATED", "sandbox": None}
    assert h.request(fn)[1] == "TERMINATED"


def test_deleting_a_missing_snapshot_succeeds() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> str:
        sb = await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        snapshot = await sb.snapshot("snap", name="deps")
        await snapshot.delete("delete")
        return "deleted"

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)
    h.step(fn)
    h.step(fn)
    h.fake.snapshots.clear()
    op = h.step(fn)
    assert op["id"] == hid("delete")
    assert "error" not in op
    assert op["data"]["result"] is None
    assert h.request(fn)[1] == "deleted"


def test_exec_output_is_binary_safe() -> None:
    h = Harness()
    h.fake.exec_stdout = b"ok \xff"

    async def async_fn(ctx: inngest.Context) -> str:
        sb = await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        return (await sb.commands.run("run", ["printf", "x"])).stdout

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)
    h.step(fn)
    assert h.request(fn)[1] == "ok �"


def test_upload_is_durable_and_records_no_data() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> int:
        sb = await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        result = await sb.files.upload("write", "/app/main.py", "print(1)")
        return result.bytes_written

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)
    op = h.step(fn)
    assert op["data"]["result"] == {"path": "/app/main.py", "bytesWritten": 8}
    assert h.fake.files == {"/app/main.py": b"print(1)"}
    assert h.request(fn)[1] == 8


def test_snapshot_runs_two_steps_in_a_span() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> str:
        sb = await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        snapshot = await sb.snapshot("snap", name="deps")
        return snapshot.status

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)

    span = [{"id": "snap", "name": "snap", "kind": "snapshot"}]
    created = h.step(fn)
    assert created["id"] == hid("snap")
    assert created["displayName"] == "Create snapshot"
    assert created["opts"] == {"origin": SDK_ORIGIN, "span": span}

    ready = h.step(fn)
    assert ready["id"] == hid("snap:wait-until-ready")
    assert ready["displayName"] == "Wait for snapshot"
    assert ready["opts"] == {"origin": SDK_ORIGIN, "span": span}
    assert ready["data"]["snapshot"]["status"] == "READY"

    assert h.request(fn)[1] == "READY"
    assert h.fake.count("POST /v2/sandboxes/{id}/snapshots") == 1


def _group_fns(
    fail: typing.Callable[[], None],
) -> tuple[
    typing.Callable[[inngest.Context], typing.Awaitable[object]],
    typing.Callable[[inngest.ContextSync], object],
]:
    async def async_fn(ctx: inngest.Context) -> object:
        async with ctx.group.sandbox("box") as sb:
            res = await sb.commands.run("run", "x")
            fail()
            return res.exit_code

    def sync_fn(ctx: inngest.ContextSync) -> object:
        with ctx.group.sandbox("box") as sb:
            res = sb.commands.run("run", "x")
            fail()
            return res.exit_code

    return async_fn, sync_fn


@pytest.mark.parametrize("is_sync", [False, True])
def test_group_sandbox_destroys_after_success(is_sync: bool) -> None:
    h = Harness()
    fn = h.function(*_group_fns(lambda: None), is_sync)
    span = [{"id": "box", "name": "Sandbox box", "kind": "sandbox"}]

    create = h.step(fn)
    assert create["id"] == hid("box")
    assert create["opts"] == {"span": span}
    assert h.fake.last("POST /v2/sandboxes").json == {
        "name": f"{RUN_ID}-box",
        "vcpu": 2,
        "memoryMb": 2048,
    }

    # A step inside the block interrupts it; that must not destroy.
    run = h.step(fn)
    assert run["opts"] == {"span": span}
    assert h.fake.count("DELETE /v2/sandboxes/{id}") == 0

    destroy = h.step(fn)
    assert destroy["id"] == hid("box:destroy")
    assert destroy["opts"] == {"span": span}
    assert h.fake.count("DELETE /v2/sandboxes/{id}") == 1

    response, output = h.request(fn)
    assert (response.status_code, output) == (200, 3)
    assert h.fake.count("DELETE /v2/sandboxes/{id}") == 1


def _raise_value_error() -> None:
    raise ValueError("boom")


def _raise_non_retriable() -> None:
    raise inngest.NonRetriableError("stop")


@pytest.mark.parametrize("is_sync", [False, True])
@pytest.mark.parametrize(
    "fail",
    [_raise_value_error, _raise_non_retriable],
    ids=["retriable", "final"],
)
def test_group_sandbox_destroys_on_error_and_ends_retries(
    is_sync: bool, fail: typing.Callable[[], None]
) -> None:
    h = Harness()
    fn = h.function(*_group_fns(fail), is_sync)
    h.step(fn)
    h.step(fn)

    # Even on the first attempt, the error destroys the sandbox in a step.
    destroy = h.step(fn, attempt=0, max_attempts=4)
    assert destroy["id"] == hid("box:destroy")
    assert h.fake.sandboxes == {}

    # A retry couldn't use the destroyed sandbox, so the error is final.
    response, body = h.request(fn, attempt=0, max_attempts=4)
    assert response.status_code == 500
    assert body["message"] in ("boom", "stop")
    assert response.headers[server_lib.HeaderKey.NO_RETRY.value] == "true"
    assert h.fake.count("DELETE /v2/sandboxes/{id}") == 1


def test_step_failing_after_group_sandbox_still_retries() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> None:
        async with ctx.group.sandbox("box"):
            pass

        async def after() -> None:
            raise ValueError("temporary")

        await ctx.step.run("after", after)

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)
    h.step(fn)
    response, body = h.request(fn, attempt=0, max_attempts=4)
    # Only the function body's errors become final, not a step's own.
    assert response.status_code == 206
    assert body[0]["id"] == hid("after")
    assert body[0]["op"] == "StepError"
    assert server_lib.HeaderKey.NO_RETRY.value not in response.headers


def test_error_without_group_sandbox_stays_retriable() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> None:
        await ctx.step.sandbox.create(
            "create", name="job", vcpu=1, memory_mb=1024
        )
        raise ValueError("boom")

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)
    response, _ = h.request(fn, attempt=0, max_attempts=4)
    assert response.status_code == 500
    assert server_lib.HeaderKey.NO_RETRY.value not in response.headers
    assert h.fake.count("DELETE /v2/sandboxes/{id}") == 0


def test_other_errors_with_is_retriable_still_retry() -> None:
    # Only sandbox errors opt out of retries through is_retriable, not any
    # error from another library that happens to have the attribute.
    class OtherError(Exception):
        is_retriable = False

    h = Harness()

    async def async_fn(ctx: inngest.Context) -> None:
        raise OtherError("boom")

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    response, _ = h.request(fn, attempt=0, max_attempts=4)
    assert response.status_code == 500
    assert server_lib.HeaderKey.NO_RETRY.value not in response.headers


@pytest.mark.parametrize(
    "options",
    [
        {"vcpu": 0},
        {"memory_mb": 0},
        # A snapshot sets the resources.
        {"snapshot_id": "0b9f6a52-8d0c-4c0e-9a3e-2f4f3b8e7d61", "vcpu": 2},
    ],
)
def test_group_sandbox_validates_options(options: dict[str, object]) -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> None:
        async with ctx.group.sandbox("box", **options):  # type: ignore[arg-type]
            pass

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    response, body = h.request(fn)
    assert response.status_code == 500
    assert body["name"] == SandboxValidationError.__name__
    assert h.fake.calls == []


@pytest.mark.parametrize("is_sync", [False, True])
def test_group_sandbox_image_survives_replay(is_sync: bool) -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> object:
        async with ctx.group.sandbox("box", image=image.inngest("base")) as sb:
            return [sb.image_ref, sb.image_digest]

    def sync_fn(ctx: inngest.ContextSync) -> object:
        with ctx.group.sandbox("box", image=image.inngest("base")) as sb:
            return [sb.image_ref, sb.image_digest]

    fn = h.function(async_fn, sync_fn, is_sync)
    h.step(fn)
    assert h.fake.last("POST /v2/sandboxes").json["image"] == "inngest/base"
    h.step(fn)
    # The destroy step replays the memoized create, with no new request.
    response, output = h.request(fn)
    assert (response.status_code, output) == (
        200,
        ["inngest/base", "sha256:" + "d" * 64],
    )
    assert h.fake.count("POST /v2/sandboxes") == 1


def test_group_sandbox_names_reused_ids_apart() -> None:
    h = Harness()

    async def async_fn(ctx: inngest.Context) -> None:
        for _ in range(2):
            async with ctx.group.sandbox("box"):
                pass

    fn = h.function(async_fn, lambda ctx: None, is_sync=False)
    h.step(fn)
    h.step(fn)
    second = h.step(fn)
    assert second["id"] == hid("box:1")
    # Each use is its own group in the trace.
    assert second["opts"] == {
        "span": [{"id": "box:1", "name": "Sandbox box", "kind": "sandbox"}]
    }
    assert [
        c.json["name"] for c in h.fake.calls if c.key == "POST /v2/sandboxes"
    ] == [
        f"{RUN_ID}-box",
        f"{RUN_ID}-box:1",
    ]
