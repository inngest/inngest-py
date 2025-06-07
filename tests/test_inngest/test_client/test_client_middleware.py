"""
You might be thinking "Why isn't this test in the "cases" directory?". We can't
test client middleware in the "cases" directory, since that shares the same
Inngest client between tests. So if we add middleware to the client then it
won't be isolated for our client middleware test
"""

import json
import typing
import unittest

import fastapi
import fastapi.testclient
import flask
import flask.logging
import flask.testing
import inngest
import inngest.fast_api
import inngest.flask
import test_core.helper
from inngest.experimental import dev_server
from test_core import base, http_proxy


class State(base.BaseState):
    def __init__(self) -> None:
        super().__init__()
        self.hook_list: list[str] = []


class TestClientMiddleware(unittest.IsolatedAsyncioTestCase):
    async def assert_state(
        self,
        state: State,
    ) -> None:
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        # Assert that the middleware hooks were called in the correct order
        assert state.hook_list == [
            "before_send_events",
            "after_send_events",
            # Entry 1
            "transform_input",
            "before_execution",
            "after_execution",
            "transform_output",
            "before_response",
            # Entry 2
            "transform_input",
            "before_execution",
            "before_send_events",
            "after_send_events",
            "after_execution",
            "transform_output",
            "before_response",
            # Entry 3
            "transform_input",
            "before_execution",
            "after_execution",
            "transform_output",
            "before_response",
        ]

        step_1_output = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert step_1_output == {"data": "transformed output"}

    async def test_async(self) -> None:
        """
        All asynchronous middleware hooks are called in the correct order
        """

        app = fastapi.FastAPI()
        fast_api_client = fastapi.testclient.TestClient(app)

        def on_request(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            return http_proxy.on_proxy_fast_api_request(
                fast_api_client,
                body=body,
                headers=headers,
                method=method,
                path=path,
            )

        proxy = http_proxy.Proxy(on_request).start()
        self.addCleanup(proxy.stop)
        state = State()

        class Middleware(inngest.Middleware):
            async def after_execution(self) -> None:
                state.hook_list.append("after_execution")

            async def after_send_events(
                self,
                result: inngest.SendEventsResult,
            ) -> None:
                state.hook_list.append("after_send_events")

            async def before_execution(self) -> None:
                state.hook_list.append("before_execution")

            async def before_response(self) -> None:
                state.hook_list.append("before_response")

            async def before_send_events(
                self,
                events: list[inngest.Event],
            ) -> None:
                state.hook_list.append("before_send_events")

            async def transform_input(
                self,
                ctx: inngest.Context | inngest.ContextSync,
                function: inngest.Function[typing.Any],
                steps: inngest.StepMemos,
            ) -> None:
                state.hook_list.append("transform_input")

            async def transform_output(
                self,
                result: inngest.TransformOutputResult,
            ) -> None:
                state.hook_list.append("transform_output")
                if result.output == "original output":
                    result.output = "transformed output"

        client = inngest.Inngest(
            api_base_url=dev_server.server.origin,
            app_id="client-middleware-fast-api",
            event_api_base_url=dev_server.server.origin,
            is_production=False,
            middleware=[Middleware],
        )

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event="trigger"),
        )
        async def fn(ctx: inngest.Context) -> None:
            state.run_id = ctx.run_id

            async def _step_1() -> str:
                return "original output"

            await ctx.step.run("step_1", _step_1)
            await ctx.step.send_event("send", inngest.Event(name="dummy"))

        inngest.fast_api.serve(app, client, [fn])
        base.register(proxy.port)
        await client.send(inngest.Event(name="trigger"))
        await self.assert_state(state)

    async def test_sync(self) -> None:
        """
        All synchronous middleware hooks are called in the correct order
        """

        app = flask.Flask(__name__)
        flask_client = app.test_client()

        def on_request(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            return http_proxy.on_proxy_flask_request(
                flask_client,
                body=body,
                headers=headers,
                method=method,
                path=path,
            )

        proxy = http_proxy.Proxy(on_request).start()
        self.addCleanup(proxy.stop)
        state = State()

        class Middleware(inngest.MiddlewareSync):
            def after_execution(self) -> None:
                state.hook_list.append("after_execution")

            def after_send_events(
                self,
                result: inngest.SendEventsResult,
            ) -> None:
                state.hook_list.append("after_send_events")

            def before_execution(self) -> None:
                state.hook_list.append("before_execution")

            def before_response(self) -> None:
                state.hook_list.append("before_response")

            def before_send_events(
                self,
                events: list[inngest.Event],
            ) -> None:
                state.hook_list.append("before_send_events")

            def transform_input(
                self,
                ctx: inngest.Context | inngest.ContextSync,
                function: inngest.Function[typing.Any],
                steps: inngest.StepMemos,
            ) -> None:
                state.hook_list.append("transform_input")

            def transform_output(
                self,
                result: inngest.TransformOutputResult,
            ) -> None:
                state.hook_list.append("transform_output")
                if result.output == "original output":
                    result.output = "transformed output"

        client = inngest.Inngest(
            api_base_url=dev_server.server.origin,
            app_id="client-middleware-flask",
            event_api_base_url=dev_server.server.origin,
            is_production=False,
            middleware=[Middleware],
        )

        @client.create_function(
            fn_id="fn",
            retries=0,
            trigger=inngest.TriggerEvent(event="trigger"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            state.run_id = ctx.run_id

            def _step_1() -> str:
                return "original output"

            ctx.step.run("step_1", _step_1)
            ctx.step.send_event("send", inngest.Event(name="dummy"))

        inngest.flask.serve(app, client, [fn])
        base.register(proxy.port)
        client.send_sync(inngest.Event(name="trigger"))
        await self.assert_state(state)
