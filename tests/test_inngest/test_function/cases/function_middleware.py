import json

import django.core.handlers.wsgi
import fastapi
import inngest
import test_core.helper
import tornado.httputil
import werkzeug.local
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.raw_request: object = None


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    class _MiddlewareSync(inngest.MiddlewareSync):
        def __init__(
            self,
            client: inngest.Inngest,
            raw_request: object,
        ) -> None:
            super().__init__(client, raw_request)
            state.raw_request = raw_request

        def after_execution(self) -> None:
            state.messages.append("hook:after_execution")

        def after_send_events(
            self,
            result: inngest.SendEventsResult,
        ) -> None:
            state.messages.append("hook:after_send_events")

        def before_execution(self) -> None:
            state.messages.append("hook:before_execution")

        def before_response(self) -> None:
            state.messages.append("hook:before_response")

        def before_send_events(self, events: list[inngest.Event]) -> None:
            state.messages.append("hook:before_send_events")

        def transform_input(
            self,
            ctx: inngest.Context,
            function: inngest.Function,
            steps: inngest.StepMemos,
        ) -> None:
            state.messages.append("hook:transform_input")

        def transform_output(
            self,
            result: inngest.TransformOutputResult,
        ) -> None:
            state.messages.append("hook:transform_output")
            if result.output == "original output":
                result.output = "transformed output"

    class _MiddlewareAsync(inngest.Middleware):
        def __init__(
            self,
            client: inngest.Inngest,
            raw_request: object,
        ) -> None:
            super().__init__(client, raw_request)
            state.raw_request = raw_request

        async def after_execution(self) -> None:
            state.messages.append("hook:after_execution")

        async def after_send_events(
            self,
            result: inngest.SendEventsResult,
        ) -> None:
            state.messages.append("hook:after_send_events")

        async def before_execution(self) -> None:
            state.messages.append("hook:before_execution")

        async def before_response(self) -> None:
            state.messages.append("hook:before_response")

        async def before_send_events(
            self,
            events: list[inngest.Event],
        ) -> None:
            state.messages.append("hook:before_send_events")

        async def transform_input(
            self,
            ctx: inngest.Context,
            function: inngest.Function,
            steps: inngest.StepMemos,
        ) -> None:
            state.messages.append("hook:transform_input")

        async def transform_output(
            self,
            result: inngest.TransformOutputResult,
        ) -> None:
            state.messages.append("hook:transform_output")
            if result.output == "original output":
                result.output = "transformed output"

    @client.create_function(
        fn_id=fn_id,
        middleware=[_MiddlewareSync],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        def _step_1() -> str:
            return "original output"

        state.messages.append("fn_logic: before step_1")
        step.run("step_1", _step_1)
        state.messages.append("fn_logic: after step_1")
        step.send_event("send", [inngest.Event(name="dummy")])
        state.messages.append("fn_logic: after send")

    @client.create_function(
        fn_id=fn_id,
        middleware=[_MiddlewareAsync],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        async def _step_1() -> str:
            return "original output"

        state.messages.append("fn_logic: before step_1")
        await step.run("step_1", _step_1)
        state.messages.append("fn_logic: after step_1")
        await step.send_event("send", [inngest.Event(name="dummy")])
        state.messages.append("fn_logic: after send")

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        if framework == server_lib.Framework.DIGITAL_OCEAN:
            assert isinstance(state.raw_request, dict)
        elif framework == server_lib.Framework.DJANGO:
            assert isinstance(
                state.raw_request, django.core.handlers.wsgi.WSGIRequest
            )
        elif framework == server_lib.Framework.FAST_API:
            assert isinstance(state.raw_request, fastapi.Request)
        elif framework == server_lib.Framework.FLASK:
            assert isinstance(state.raw_request, werkzeug.local.LocalProxy)
        elif framework == server_lib.Framework.TORNADO:
            assert isinstance(
                state.raw_request, tornado.httputil.HTTPServerRequest
            )
        else:
            raise ValueError(f"unknown framework: {framework.value}")

        # Assert that the middleware hooks were called in the correct order
        assert state.messages == [
            # Entry 1
            "hook:transform_input",
            "hook:before_execution",
            "fn_logic: before step_1",
            "hook:after_execution",
            "hook:transform_output",
            "hook:before_response",
            # Entry 2
            "hook:transform_input",
            "fn_logic: before step_1",
            "hook:before_execution",
            "fn_logic: after step_1",
            "hook:before_send_events",
            "hook:after_send_events",
            "hook:after_execution",
            "hook:transform_output",
            "hook:before_response",
            # Entry 3
            "hook:transform_input",
            "fn_logic: before step_1",
            "fn_logic: after step_1",
            "hook:before_execution",
            "fn_logic: after send",
            "hook:after_execution",
            "hook:transform_output",
            "hook:before_response",
        ]

        step_1_output = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert step_1_output == {"data": "transformed output"}

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
