import typing

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    step_output: dict[str, dict[str, int]] = {}  # noqa: RUF012


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
    def fn_receiver_sync(ctx: inngest.ContextSync) -> dict[str, dict[str, int]]:
        return {"foo": {"bar": 1}}

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sender_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        state.step_output = ctx.step.invoke(
            "invoke",
            function=fn_receiver_sync,
        )

    @client.create_function(
        fn_id=f"{fn_id}/invokee",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    async def fn_receiver_async(
        ctx: inngest.Context,
    ) -> dict[str, dict[str, int]]:
        return {"foo": {"bar": 1}}

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_sender_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        state.step_output = await ctx.step.invoke(
            "invoke",
            function=fn_receiver_async,
        )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert state.step_output == {"foo": {"bar": 1}}

    fn: list[inngest.Function[typing.Any]]
    if is_sync:
        fn = [fn_receiver_sync, fn_sender_sync]
    else:
        fn = [fn_receiver_async, fn_sender_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
