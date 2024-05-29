import datetime
import json

import inngest
import tests.helper

from . import base

_TEST_NAME = "invoke_timeout"


class _State(base.BaseState):
    step_output: object = None


def create(
    client: inngest.Inngest,
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=f"{fn_id}/invokee",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    def fn_receiver_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        step.sleep("sleep", 60_000)

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sender_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id
        state.step_output = step.invoke(
            "invoke",
            function=fn_receiver_sync,
            timeout=datetime.timedelta(seconds=1),
        )

    @client.create_function(
        fn_id=f"{fn_id}/invokee",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    async def fn_receiver_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        await step.sleep("sleep", 60_000)

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_sender_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id
        state.step_output = await step.invoke(
            "invoke",
            function=fn_receiver_async,
            timeout=datetime.timedelta(seconds=1),
        )

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        assert json.loads(run.output) == {
            "code": "step_errored",
            "message": "Timed out waiting for invoked function to complete",
            "name": "InngestInvokeTimeoutError",
            "stack": None,
        }

    if is_sync:
        fn = [fn_receiver_sync, fn_sender_sync]
    else:
        fn = [fn_receiver_async, fn_sender_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
