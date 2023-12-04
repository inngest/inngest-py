import json

import inngest
import tests.helper

from . import base

_TEST_NAME = "two_steps"


class _State(base.BaseState):
    step_1_counter = 0
    step_1_output: object = None
    step_2_counter = 0


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @inngest.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        def step_1() -> list[dict[str, object]]:
            state.step_1_counter += 1
            return [{"foo": {"bar": 1}}]

        state.step_1_output = step.run("step_1", step_1)

        def step_2() -> None:
            state.step_2_counter += 1

        step.run("step_2", step_2)

    @inngest.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        async def step_1() -> list[dict[str, object]]:
            state.step_1_counter += 1
            return [{"foo": {"bar": 1}}]

        state.step_1_output = await step.run("step_1", step_1)

        async def step_2() -> None:
            state.step_2_counter += 1

        await step.run("step_2", step_2)

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert (
            state.step_1_counter == 1
        ), f"step_1_counter: {state.step_1_counter}"
        assert (
            state.step_2_counter == 1
        ), f"step_2_counter: {state.step_2_counter}"
        assert state.step_1_output == [{"foo": {"bar": 1}}], state.step_1_output

        step_1_output_in_api = json.loads(
            tests.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert step_1_output_in_api == {
            "data": [{"foo": {"bar": 1}}]
        }, step_1_output_in_api

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
