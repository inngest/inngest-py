"""
When an invoked function fails, `step.invoke` raises a NonRetriableError.
"""

import json
import typing

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    raised_error: typing.Optional[inngest.StepError] = None


class MyException(Exception):
    pass


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
    def fn_receiver_sync(ctx: inngest.ContextSync) -> None:
        raise MyException("oh no")

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sender_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id

        try:
            ctx.step.invoke(
                "invoke",
                function=fn_receiver_sync,
            )
        except inngest.StepError as err:
            state.raised_error = err
            raise err

    @client.create_function(
        fn_id=f"{fn_id}/invokee",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    async def fn_receiver_async(ctx: inngest.Context) -> None:
        raise MyException("oh no")

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_sender_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        try:
            await ctx.step.invoke(
                "invoke",
                function=fn_receiver_async,
            )
        except inngest.StepError as err:
            state.raised_error = err
            raise err

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.FAILED,
        )
        assert run.output is not None
        output = json.loads(run.output)
        assert output["message"] == "oh no"
        assert output["name"] == "MyException"

        # `step.invoke` raises an error that contains details about the invoked
        # function's error.
        assert state.raised_error is not None
        assert state.raised_error.message == "oh no"
        assert state.raised_error.name == "MyException"
        assert isinstance(state.raised_error.stack, str)

    if is_sync:
        fn = [fn_receiver_sync, fn_sender_sync]
    else:
        fn = [fn_receiver_async, fn_sender_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
