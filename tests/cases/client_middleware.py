import json

import inngest
import tests.helper

from . import base

_TEST_NAME = "client_middleware"


class _State(base.BaseState):
    def __init__(self) -> None:
        self.hook_list: list[str] = []


def create(
    client: inngest.Inngest,
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    middleware: type[inngest.Middleware | inngest.MiddlewareSync]
    if is_sync:

        class _MiddlewareSync(inngest.MiddlewareSync):
            def after_execution(self) -> None:
                state.hook_list.append("after_execution")

            def before_response(self) -> None:
                state.hook_list.append("before_response")

            def before_execution(self) -> None:
                state.hook_list.append("before_execution")

            def transform_input(
                self,
                ctx: inngest.Context,
            ) -> inngest.Context:
                state.hook_list.append("transform_input")
                return ctx

            def transform_output(
                self,
                output: inngest.Output,
            ) -> inngest.Output:
                state.hook_list.append("transform_output")
                if output.data == "original output":
                    output.data = "transformed output"
                return output

        middleware = _MiddlewareSync

    else:

        class _MiddlewareAsync(inngest.Middleware):
            async def after_execution(self) -> None:
                state.hook_list.append("after_execution")

            async def before_response(self) -> None:
                state.hook_list.append("before_response")

            async def before_execution(self) -> None:
                state.hook_list.append("before_execution")

            async def transform_input(
                self,
                ctx: inngest.Context,
            ) -> inngest.Context:
                state.hook_list.append("transform_input")
                return ctx

            async def transform_output(
                self,
                output: inngest.Output,
            ) -> inngest.Output:
                state.hook_list.append("transform_output")
                if output.data == "original output":
                    output.data = "transformed output"
                return output

        middleware = _MiddlewareAsync

    @client.create_function(
        fn_id=fn_id,
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

        step.run("step_1", _step_1)

        def _step_2() -> None:
            pass

        step.run("step_2", _step_2)

    @client.create_function(
        fn_id=fn_id,
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

        await step.run("step_1", _step_1)

        async def _step_2() -> None:
            pass

        await step.run("step_2", _step_2)

    def run_test(self: base.TestClass) -> None:
        self.client.add_middleware(middleware)
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        # Assert that the middleware hooks were called in the correct order
        assert state.hook_list == [
            # Entry 1
            "transform_input",
            "before_execution",
            "after_execution",
            "transform_output",
            "before_response",
            # Entry 2
            "transform_input",
            "before_execution",
            "after_execution",
            "transform_output",
            "before_response",
            # Entry 3
            "transform_input",
            "before_execution",
            "after_execution",
            "transform_output",
            "before_response",
        ], state.hook_list

        step_1_output = json.loads(
            tests.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert step_1_output == {"data": "transformed output"}, step_1_output

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
