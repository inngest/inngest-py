import json

import inngest
import inngest.experimental
import tests.helper

from . import base

_TEST_NAME = "function_middleware"


class _State(base.BaseState):
    def __init__(self) -> None:
        self.hook_list: list[str] = []


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    class _MiddlewareSync(inngest.experimental.MiddlewareSync):
        def after_execution(self) -> None:
            state.hook_list.append("after_execution")

        def before_response(self) -> None:
            # This hook is not called for function middleware but we'll include
            # in anyway to verify that.
            state.hook_list.append("before_response")

        def before_execution(self) -> None:
            state.hook_list.append("before_execution")

        def transform_input(
            self,
            call_input: inngest.experimental.TransformableInput,
        ) -> inngest.experimental.TransformableInput:
            state.hook_list.append("transform_input")
            return call_input

        def transform_output(
            self,
            output: object,
        ) -> object:
            state.hook_list.append("transform_output")
            if output == "original output":
                return "transformed output"
            return output

    class _MiddlewareAsync(inngest.experimental.Middleware):
        async def after_execution(self) -> None:
            state.hook_list.append("after_execution")

        async def before_response(self) -> None:
            # This hook is not called for function middleware but we'll include
            # in anyway to verify that.
            state.hook_list.append("before_response")

        async def before_execution(self) -> None:
            state.hook_list.append("before_execution")

        async def transform_input(
            self,
            call_input: inngest.experimental.TransformableInput,
        ) -> inngest.experimental.TransformableInput:
            state.hook_list.append("transform_input")
            return call_input

        async def transform_output(
            self,
            output: object,
        ) -> object:
            state.hook_list.append("transform_output")
            if output == "original output":
                return "transformed output"
            return output

    @inngest.create_function(
        fn_id=test_name,
        middleware=[_MiddlewareSync],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        *,
        logger: inngest.Logger,
        step: inngest.StepSync,
        run_id: str,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        def _step_1() -> str:
            return "original output"

        step.run("step_1", _step_1)

        def _step_2() -> None:
            pass

        step.run("step_2", _step_2)

    @inngest.create_function(
        fn_id=test_name,
        middleware=[_MiddlewareAsync],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        *,
        logger: inngest.Logger,
        step: inngest.Step,
        run_id: str,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        async def _step_1() -> str:
            return "original output"

        await step.run("step_1", _step_1)

        async def _step_2() -> None:
            pass

        await step.run("step_2", _step_2)

    def run_test(self: base.TestClass) -> None:
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
            # Entry 2
            "transform_input",
            "before_execution",
            "after_execution",
            "transform_output",
            # Entry 3
            "transform_input",
            "before_execution",
            "after_execution",
            "transform_output",
        ], state.hook_list

        step_1_output = json.loads(
            tests.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert step_1_output == "transformed output", step_1_output

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
