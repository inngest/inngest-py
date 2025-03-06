import datetime
import json
import typing

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    raised_err: typing.Optional[Exception] = None


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
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
        try:
            step.invoke(
                "invoke",
                function=fn_receiver_sync,
                timeout=datetime.timedelta(seconds=1),
            )
        except Exception as e:
            state.raised_err = e
            raise e

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
        try:
            await step.invoke(
                "invoke",
                function=fn_receiver_async,
                timeout=datetime.timedelta(seconds=1),
            )
        except Exception as e:
            state.raised_err = e
            raise e

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.FAILED,
        )

        assert state.raised_err is not None
        assert isinstance(state.raised_err, inngest.StepError)
        assert state.raised_err.name == "InngestInvokeTimeoutError"

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
