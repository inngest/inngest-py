import asyncio
import datetime
import hashlib
import json
import time
import typing
from unittest import mock

import httpx
import pytest

import inngest
from inngest._internal import net, server_lib
from inngest._internal.checkpoint import Checkpointer
from inngest._internal.comm_lib.handler import CommHandler
from inngest._internal.comm_lib.models import CommRequest, CommResponse
from inngest.experimental import create_defer


def request(**overrides: object) -> CommRequest:
    ctx = {
        "attempt": 0,
        "max_attempts": 3,
        "disable_immediate_execution": False,
        "run_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "fn_id": "05bb848e-3cc7-4870-b2a0-18881cd9c40a",
        "qi_id": "queue-reference",
        "stack": {"stack": []},
    }
    ctx.update(overrides)
    return CommRequest(
        body=json.dumps(
            {
                "ctx": ctx,
                "event": {"name": "test", "data": {}},
                "events": [{"name": "test", "data": {}}],
                "steps": {},
                "use_api": False,
            }
        ).encode(),
        headers={},
        public_path=None,
        query_params={"fnId": "test-fn"},
        raw_request=None,
        request_url="http://localhost/api/inngest",
        serve_origin=None,
        serve_path=None,
    )


@pytest.mark.parametrize("sync", [True, False])
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "off",
        "override_off",
        "missing_context",
        "connect",
        "targeted",
        "disable_immediate",
        "failure",
        "permanent",
        "retry_reset",
        "transport_failure",
        "lost_ack",
        "auth_rotation",
        "deadline",
        "wait",
        "middleware",
        "middleware_fallback",
        "bad_json",
        "nested",
    ],
)
def test_execution(sync: bool, scenario: str) -> None:
    requests: list[httpx.Request] = []
    callbacks: list[str] = []
    attempts: list[int] = []
    lifecycle: list[str] = []
    transforms: list[str] = []
    state: dict[str, object] = {}

    def transport(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        body = json.loads(req.content)
        for step in body["steps"]:
            timing = step["timing"]
            assert isinstance(timing["a"], int)
            assert isinstance(timing["b"], int)
            assert invocation_started_ns <= timing["a"] <= time.time_ns()
            assert 0 <= timing["b"] < 10_000_000_000
            assert timing["a"] + timing["b"] <= time.time_ns()
        assert body["fn_id"] == "05bb848e-3cc7-4870-b2a0-18881cd9c40a"
        assert body["qi_id"] == "queue-reference"
        assert req.headers["x-inngest-env"] == "test-branch"
        assert req.headers["authorization"].startswith("Bearer ")
        assert "signkey-prod" not in req.headers["authorization"]
        if scenario in ("transport_failure", "middleware_fallback"):
            return httpx.Response(503)
        if scenario == "auth_rotation" and len(requests) == 1:
            return httpx.Response(401)
        for step in body["steps"]:
            state[step["id"]] = step["data"]
        if scenario == "lost_ack" and len(requests) == 1:
            raise httpx.ReadTimeout("response lost after commit")
        return httpx.Response(200)

    class Middleware(inngest.MiddlewareSync):
        def before_execution(self) -> None:
            lifecycle.append("before")

        def after_execution(self) -> None:
            lifecycle.append("after")

        def before_response(self) -> None:
            lifecycle.append("response")

        def transform_output(
            self, result: inngest.TransformOutputResult
        ) -> None:
            if result.step is not None:
                transforms.append(result.step.id)
                if scenario in ("middleware", "middleware_fallback"):
                    result.output = {"wrapped": result.output}

    client = inngest.Inngest(
        app_id="test",
        is_production=False,
        checkpointing=(
            False
            if scenario == "off"
            else inngest.Checkpointing(
                max_runtime=datetime.timedelta(seconds=1),
            )
        ),
        env="test-branch",
        signing_key="signkey-prod-aabb",
        middleware=[Middleware],
    )
    client._signing_key_fallback = "signkey-prod-ccdd"
    sync_http = httpx.Client(transport=httpx.MockTransport(transport))
    async_http = net.ThreadAwareAsyncHTTPClient(
        transport=httpx.MockTransport(transport)
    ).initialize()
    client._http_client._http_client_sync = sync_http
    client._http_client._http_client = async_http

    def callback(name: str) -> object:
        callbacks.append(name)
        if name == "b" and scenario in ("failure", "retry_reset"):
            raise ValueError("retry me")
        if name == "b" and scenario == "permanent":
            raise inngest.NonRetriableError("stop")
        if scenario == "bad_json":
            return object()
        return {"name": name}

    def fn_sync(ctx: inngest.ContextSync) -> object:
        if scenario == "nested":
            return ctx.step.run(
                "outer", lambda: ctx.step.run("inner", lambda: 1)
            )
        a = ctx.step.run("a", callback, "a")
        attempts.append(ctx.attempt)
        if scenario == "wait":
            ctx.step.sleep("wait", datetime.timedelta(seconds=1))
        b = ctx.step.run("b", callback, "b")
        return [a, b]

    async def fn_async(ctx: inngest.Context) -> object:
        async def cb(name: str) -> object:
            return callback(name)

        if scenario == "nested":

            async def outer() -> object:
                return await ctx.step.run("inner", cb, "inner")

            return await ctx.step.run("outer", outer)
        a = await ctx.step.run("a", cb, "a")
        attempts.append(ctx.attempt)
        if scenario == "wait":
            await ctx.step.sleep("wait", datetime.timedelta(seconds=1))
        b = await ctx.step.run("b", cb, "b")
        return [a, b]

    fn = client.create_function(
        fn_id="fn",
        trigger=inngest.TriggerEvent(event="test"),
        checkpointing=False if scenario == "override_off" else None,
    )(fn_sync if sync else fn_async)
    handler = CommHandler(
        client=client,
        functions=[fn],
        framework=server_lib.Framework.FAST_API,
        enable_unauthed_sync=None,
        streaming=None,
    )
    req = request(
        attempt=2 if scenario == "retry_reset" else 0,
        qi_id=None if scenario == "missing_context" else "queue-reference",
        disable_immediate_execution=scenario == "disable_immediate",
    )
    req.is_connect = scenario == "connect"
    if scenario == "targeted":
        req.query_params = {
            "fnId": "test-fn",
            "stepId": hashlib.sha1(b"a").hexdigest(),
        }

    invocation_started_ns = time.time_ns()

    # A runtime already consumed before a new step must plan, not execute it.
    with mock.patch(
        "inngest._internal.checkpoint.Checkpointer.expired",
        new_callable=mock.PropertyMock,
        return_value=scenario == "deadline",
    ):

        async def post() -> CommResponse:
            return await handler.post(req)

        res = handler.post_sync(req) if sync else asyncio.run(post())

    if scenario in (
        "success",
        "lost_ack",
        "auth_rotation",
        "middleware",
    ):
        assert res.status_code == 200, res.body
        expected = [{"name": "a"}, {"name": "b"}]
        assert res.body == (
            [{"wrapped": v} for v in expected]
            if scenario == "middleware"
            else expected
        )
        assert callbacks == ["a", "b"]
        assert len(state) == 2
        assert len(requests) == (
            3 if scenario in ("lost_ack", "auth_rotation") else 2
        )
    elif scenario == "permanent":
        assert res.status_code == 500
        assert res.no_retry
        assert callbacks == ["a", "b"]
    elif scenario == "bad_json":
        assert res.status_code == 500
        assert not requests
    else:
        assert res.status_code == 206, res.body
        assert isinstance(res.body, list)
        body = typing.cast(list[dict[str, object]], res.body)
        assert len(body) == 1
        if scenario in ("failure", "nested"):
            assert body[0]["op"] == "StepError"
        elif scenario == "wait":
            assert body[0]["op"] == "Sleep"
        elif scenario in ("deadline", "disable_immediate"):
            assert body[0]["op"] == "StepPlanned"
            assert callbacks == []
        else:
            assert body[0]["op"] == "StepRun"
            assert callbacks == ["a"]
    assert lifecycle == (
        ["before", "response"]
        if scenario == "permanent"
        else ["before", "after", "response"]
    )
    if scenario == "retry_reset":
        assert attempts == []
        assert not requests
    if scenario == "auth_rotation":
        assert (
            requests[1].headers["authorization"]
            == requests[2].headers["authorization"]
        )
    if scenario == "middleware_fallback":
        assert transforms == ["a"]
        assert typing.cast(list[dict[str, object]], res.body)[0]["data"] == {
            "wrapped": {"name": "a"}
        }
    if scenario in (
        "off",
        "override_off",
        "missing_context",
        "connect",
        "targeted",
        "disable_immediate",
    ):
        assert not requests
    sync_http.close()
    asyncio.run(async_http.aclose())


@pytest.mark.parametrize("sync", [True, False])
def test_deferred_operation_is_yielded_with_its_step(sync: bool) -> None:
    checkpoints: list[httpx.Request] = []
    callbacks: list[str] = []

    def transport(req: httpx.Request) -> httpx.Response:
        checkpoints.append(req)
        return httpx.Response(200)

    client = inngest.Inngest(
        app_id="test", is_production=False, checkpointing=True
    )
    sync_http = httpx.Client(transport=httpx.MockTransport(transport))
    async_http = net.ThreadAwareAsyncHTTPClient(
        transport=httpx.MockTransport(transport)
    ).initialize()
    client._http_client._http_client_sync = sync_http
    client._http_client._http_client = async_http

    def child(ctx: inngest.ContextSync) -> None:
        pass

    target = create_defer(client, fn_id="child")(child)

    def work(ctx: inngest.Context | inngest.ContextSync) -> int:
        callbacks.append("work")
        ctx.defer("child", function=target, data={"from": "step"})
        return 1

    def fn_sync(ctx: inngest.ContextSync) -> int:
        first = ctx.step.run("work", lambda: work(ctx))
        return ctx.step.run("next", lambda: first + 1)

    async def fn_async(ctx: inngest.Context) -> int:
        async def first() -> int:
            return work(ctx)

        value = await ctx.step.run("work", first)

        async def second() -> int:
            return value + 1

        return await ctx.step.run("next", second)

    fn = client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="test")
    )(fn_sync if sync else fn_async)
    handler = CommHandler(
        client=client,
        functions=[fn, target],
        framework=server_lib.Framework.FAST_API,
        enable_unauthed_sync=None,
        streaming=None,
    )
    req = request()

    async def post() -> CommResponse:
        return await handler.post(req)

    try:
        response = handler.post_sync(req) if sync else asyncio.run(post())
        assert response.status_code == 206
        body = typing.cast(list[dict[str, object]], response.body)
        assert [op["op"] for op in body] == ["DeferAdd", "StepRun"]
        assert body[1]["data"] == 1
        assert not checkpoints

        # Replay skips the callback but keeps its deferred operation durable.
        payload = json.loads(req.body)
        payload["steps"] = {body[1]["id"]: {"data": 1}}
        payload["defers"] = {body[0]["id"]: {"abortable": True}}
        req.body = json.dumps(payload).encode()
        response = handler.post_sync(req) if sync else asyncio.run(post())
        assert response.status_code == 200
        assert response.body == 2
        assert callbacks == ["work"]
        assert len(checkpoints) == 1
    finally:
        sync_http.close()
        asyncio.run(async_http.aclose())


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        inngest.Checkpointing(max_runtime=datetime.timedelta(seconds=-1))
    with pytest.raises(ValueError):
        inngest.Checkpointing.model_validate({"buffered_steps": 2})


@pytest.mark.parametrize(
    "setting",
    [
        True,
        False,
        inngest.Checkpointing(max_runtime=datetime.timedelta(microseconds=1)),
    ],
)
def test_registration_and_override(
    setting: inngest.Checkpointing | bool,
) -> None:
    client = inngest.Inngest(
        app_id="test", is_production=False, checkpointing=setting
    )

    @client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="test")
    )
    def fn(ctx: inngest.ContextSync) -> None:
        pass

    config = fn.get_config("http://localhost/api/inngest").main.to_dict()
    assert isinstance(config, dict)
    if setting is False:
        assert "checkpoint" not in config
    else:
        assert config["checkpoint"] == {
            "batch_steps": 1,
            "batch_interval": "0s",
            "max_runtime": "0.000000s" if setting is True else "0.000001s",
        }
    connect = fn.get_config("wss://localhost").main.to_dict()
    assert isinstance(connect, dict)
    assert "checkpoint" not in connect

    @client.create_function(
        fn_id="override",
        trigger=inngest.TriggerEvent(event="test"),
        checkpointing=not bool(setting),
    )
    def override(ctx: inngest.ContextSync) -> None:
        pass

    overridden = override.get_config(
        "http://localhost/api/inngest"
    ).main.to_dict()
    assert isinstance(overridden, dict)
    assert ("checkpoint" in overridden) is (setting is False)


@pytest.mark.parametrize("sync", [True, False])
@pytest.mark.parametrize(
    "status,expected_attempts",
    [
        (400, 1),
        (401, 1),
        (403, 1),
        (404, 1),
        (409, 1),
        (413, 1),
        (429, 3),
        (500, 3),
        (503, 3),
    ],
)
def test_transport_falls_back_without_retrying_permanent_errors(
    sync: bool,
    status: int,
    expected_attempts: int,
) -> None:
    client = inngest.Inngest(app_id="test", is_production=False)
    req = server_lib.ServerRequest.model_validate_json(request().body)
    checkpointer = Checkpointer(client, req, inngest.Checkpointing())
    count = 0

    def respond(req: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(status)

    transport = httpx.MockTransport(respond)
    client._http_client._http_client_sync = httpx.Client(transport=transport)
    client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
        transport=transport
    ).initialize()
    step: dict[str, object] = {"id": "test", "op": "StepRun", "data": None}
    if sync:
        assert not checkpointer.persist_sync(step)
    else:
        assert not asyncio.run(checkpointer.persist(step))
    assert count == expected_attempts
    client._http_client._http_client_sync.close()
    asyncio.run(client._http_client._http_client.aclose())


def test_async_cancellation_does_not_start_another_step_or_retry() -> None:
    async def run() -> None:
        client = inngest.Inngest(app_id="test", is_production=False)
        req = server_lib.ServerRequest.model_validate_json(request().body)
        checkpointer = Checkpointer(client, req, inngest.Checkpointing())
        entered = asyncio.Event()
        count = 0

        async def respond(req: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            entered.set()
            await asyncio.Event().wait()
            return httpx.Response(200)

        client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
            transport=httpx.MockTransport(respond)
        ).initialize()
        task = asyncio.create_task(
            checkpointer.persist({"id": "a", "data": None})
        )
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert count == 1
        await client._http_client._http_client.aclose()

    asyncio.run(run())
