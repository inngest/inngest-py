import asyncio
import functools
import typing

import fastapi
import fastapi.testclient
import httpx
import pytest

import inngest
import inngest.fast_api
from inngest._internal import errors


def _post_function(
    client: inngest.Inngest,
    fn: inngest.Function[typing.Any],
    *,
    failure: bool = False,
    steps: dict[str, object] | None = None,
) -> httpx.Response:
    app = fastapi.FastAPI()
    inngest.fast_api.serve(app, client, [fn])
    event = {"name": "test", "data": {"value": "input"}}
    with fastapi.testclient.TestClient(app) as http:
        return http.post(
            "/api/inngest",
            params={
                "fnId": fn.on_failure_fn_id if failure else fn.id,
                "stepId": "step",
            },
            json={
                "ctx": {
                    "attempt": 0,
                    "disable_immediate_execution": False,
                    "run_id": "test-run",
                    "stack": {"stack": list(steps or {})},
                },
                "event": event,
                "events": [event],
                "steps": steps or {},
                "use_api": False,
            },
        )


@pytest.mark.parametrize("use_partial", [False, True])
def test_async_callable_handler_returns_result(use_partial: bool) -> None:
    client = inngest.Inngest(app_id="test", is_production=False)

    class Handler:
        async def __call__(self, ctx: inngest.Context) -> str:
            await asyncio.sleep(0)
            return f"processed:{ctx.event.data['value']}"

    handler = Handler()
    fn = client.create_function(
        fn_id="callable", trigger=inngest.TriggerEvent(event="test")
    )(functools.partial(handler) if use_partial else handler)

    response = _post_function(client, fn)
    assert response.status_code == 200
    assert response.json() == "processed:input"


@pytest.mark.parametrize("use_partial", [False, True])
def test_async_callable_on_failure_returns_result(use_partial: bool) -> None:
    client = inngest.Inngest(app_id="test", is_production=False)

    class OnFailure:
        async def __call__(self, ctx: inngest.Context) -> str:
            await asyncio.sleep(0)
            return f"recovered:{ctx.event.data['value']}"

    on_failure = OnFailure()

    @client.create_function(
        fn_id="callable",
        trigger=inngest.TriggerEvent(event="test"),
        on_failure=(
            functools.partial(on_failure) if use_partial else on_failure
        ),
    )
    async def fn(ctx: inngest.Context) -> None:
        raise ValueError("failed")

    response = _post_function(client, fn, failure=True)
    assert response.status_code == 200
    assert response.json() == "recovered:input"


@pytest.mark.parametrize("use_partial", [False, True])
def test_sync_callable_handler_returns_result(use_partial: bool) -> None:
    client = inngest.Inngest(app_id="test", is_production=False)

    class Handler:
        def __call__(self, ctx: inngest.ContextSync) -> str:
            return ctx.step.run("work", lambda: "processed:input")

    handler = Handler()
    fn = client.create_function(
        fn_id="callable", trigger=inngest.TriggerEvent(event="test")
    )(functools.partial(handler) if use_partial else handler)

    response = _post_function(client, fn)
    assert response.status_code == 206
    step = response.json()[0]
    assert step["data"] == "processed:input"
    response = _post_function(client, fn, steps={step["id"]: step["data"]})
    assert response.status_code == 200
    assert response.json() == "processed:input"


@pytest.mark.parametrize("output", [None, False, 0, "done"])
def test_async_callable_handler_replays_step_result(output: object) -> None:
    client = inngest.Inngest(app_id="test", is_production=False)
    calls: list[str] = []

    class Handler:
        async def __call__(self, ctx: inngest.Context) -> object:
            async def work() -> object:
                calls.append("work")
                return output

            return await ctx.step.run("work", work)

    fn = client.create_function(
        fn_id="callable", trigger=inngest.TriggerEvent(event="test")
    )(Handler())

    response = _post_function(client, fn)
    assert response.status_code == 206
    step = response.json()[0]
    assert step["data"] == output
    response = _post_function(client, fn, steps={step["id"]: step["data"]})
    assert response.status_code == 200
    assert response.json() == output
    assert calls == ["work"]


@pytest.mark.parametrize("use_partial", [False, True])
def test_sync_function_rejects_async_callable_on_failure(
    use_partial: bool,
) -> None:
    client = inngest.Inngest(app_id="test", is_production=False)

    class OnFailure:
        async def __call__(self, ctx: inngest.Context) -> None:
            pass

    on_failure = OnFailure()
    with pytest.raises(errors.Error, match="non-async function cannot have"):

        @client.create_function(
            fn_id="callable",
            trigger=inngest.TriggerEvent(event="test"),
            on_failure=(
                functools.partial(on_failure) if use_partial else on_failure
            ),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            pass


@pytest.mark.parametrize("use_partial", [False, True])
def test_async_callable_rejects_sync_on_failure(use_partial: bool) -> None:
    client = inngest.Inngest(app_id="test", is_production=False)

    class Handler:
        async def __call__(self, ctx: inngest.Context) -> None:
            pass

    def on_failure(ctx: inngest.ContextSync) -> None:
        pass

    handler = Handler()
    with pytest.raises(errors.Error, match="async function cannot have"):
        client.create_function(
            fn_id="callable",
            trigger=inngest.TriggerEvent(event="test"),
            on_failure=on_failure,
        )(functools.partial(handler) if use_partial else handler)


def test_async_callable_handler_propagates_error() -> None:
    client = inngest.Inngest(app_id="test", is_production=False)

    class Handler:
        async def __call__(self, ctx: inngest.Context) -> None:
            await asyncio.sleep(0)
            raise ValueError("handler failed")

    fn = client.create_function(
        fn_id="callable", trigger=inngest.TriggerEvent(event="test")
    )(Handler())

    response = _post_function(client, fn)
    assert response.status_code == 500
    assert response.json()["name"] == "ValueError"
    assert response.json()["message"] == "handler failed"


def test_sync_fn_with_async_on_failure() -> None:
    """
    Test that a sync function can not have an async on_failure handler.
    """

    client = inngest.Inngest(app_id="test", is_production=False)

    async def on_failure(ctx: inngest.Context) -> None:
        pass

    with pytest.raises(errors.Error) as e:

        @client.create_function(
            fn_id="foo",
            trigger=inngest.TriggerEvent(event="foo"),
            on_failure=on_failure,
        )
        def fn(ctx: inngest.ContextSync) -> None:
            pass

    assert (
        str(e.value)
        == "a non-async function cannot have an async on_failure handler (function foo)"
    )


def test_async_fn_with_sync_on_failure() -> None:
    """
    Test that an async function can not have a sync on_failure handler.
    """

    client = inngest.Inngest(app_id="test", is_production=False)

    def on_failure(ctx: inngest.ContextSync) -> None:
        pass

    with pytest.raises(errors.Error) as e:

        @client.create_function(
            fn_id="foo",
            trigger=inngest.TriggerEvent(event="foo"),
            on_failure=on_failure,
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

    assert (
        str(e.value)
        == "an async function cannot have a non-async on_failure handler (function foo)"
    )
