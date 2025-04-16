import json

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    after_step_counter = 0
    step_2_catch_counter = 0
    step_1_counter = 0
    step_2_counter = 0


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    # Set retries to something high to ensure that we raise a non-retriable
    # error.
    retries = 5

    @client.create_function(
        fn_id=fn_id,
        retries=retries,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        def step_1() -> None:
            state.step_1_counter += 1

            def step_2() -> None:
                # Should reach here.
                state.step_2_counter += 1

            try:
                step.run("step_2", step_2)
            except Exception:
                # Can't catch this error.
                state.step_2_catch_counter += 1

        step.run("step_1", step_1)
        state.after_step_counter += 1

    @client.create_function(
        fn_id=fn_id,
        retries=retries,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        async def step_1() -> None:
            state.step_1_counter += 1

            async def step_2() -> None:
                # Should not reach here.
                state.step_2_counter += 1

            try:
                await step.run("step_2", step_2)
            except Exception:
                # Can't catch this error.
                state.step_2_catch_counter += 1

        await step.run("step_1", step_1)
        state.after_step_counter += 1

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        assert json.loads(run.output) == {
            "code": "step_errored",
            "message": "Nested steps are not supported.",
            "name": "CodedError",
            "stack": "inngest._internal.errors.CodedError: Nested steps are not supported.\n",
        }

        assert state.step_1_counter == 1
        assert state.step_2_counter == 0
        assert state.step_2_catch_counter == 0
        assert state.after_step_counter == 0

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
