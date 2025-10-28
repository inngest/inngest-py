"""
Use `step` decorator to "stepify" a function
"""

import json

import inngest
import inngest.experimental
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    step_1_counter = 0
    step_1_output: object = None
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

    @inngest.experimental.step("step_1")
    def step_1_sync(msg: str) -> list[dict[str, inngest.JSON]]:
        state.step_1_counter += 1
        return [{"foo": {"bar": 1}, "empty": None, "msg": msg}]

    @inngest.experimental.step("step_1")
    async def step_1_async(msg: str) -> list[dict[str, inngest.JSON]]:
        state.step_1_counter += 1
        return [{"foo": {"bar": 1}, "empty": None, "msg": msg}]

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        state.step_1_output = step_1_sync("Hello")

        def step_2() -> None:
            state.step_2_counter += 1

        ctx.step.run("step_2", step_2)

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        state.step_1_output = await step_1_async("Hello")

        async def step_2() -> None:
            state.step_2_counter += 1

        await ctx.step.run("step_2", step_2)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.step_1_counter == 1
        assert state.step_2_counter == 1
        assert state.step_1_output == [
            {"empty": None, "foo": {"bar": 1}, "msg": "Hello"}
        ]

        step_1_output_in_api = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert step_1_output_in_api == {
            "data": [{"empty": None, "foo": {"bar": 1}, "msg": "Hello"}]
        }

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
