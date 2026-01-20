import datetime
import typing
import unittest.mock

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    step_1a_counter = 0
    step_1b_counter = 0
    step_after_counter = 0
    parallel_output: typing.Any = None
    request_counter = 0


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = test_name
    state = _State()

    @client.create_function(
        fn_id=f"{fn_id}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    def fn_child_sync(ctx: inngest.ContextSync) -> str:
        ctx.step.sleep("sleep", datetime.timedelta(seconds=1))
        return "done"

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        state.request_counter += 1

        def _step_1a() -> int:
            state.step_1a_counter += 1
            return 1

        def _step_1b() -> int:
            state.step_1b_counter += 1
            return 2

        state.parallel_output = ctx.group.parallel(
            (
                lambda: ctx.step.invoke("invoke", function=fn_child_sync),
                lambda: ctx.step.run("1a", _step_1a),
                lambda: ctx.step.run("1b", _step_1b),
                lambda: ctx.step.send_event(
                    "send", events=inngest.Event(name="noop")
                ),
            )
        )

        def _step_after() -> None:
            state.step_after_counter += 1

        ctx.step.run("after", _step_after)

    @client.create_function(
        fn_id=f"{fn_id}/child",
        retries=0,
        trigger=inngest.TriggerEvent(event="never"),
    )
    async def fn_child_async(ctx: inngest.Context) -> str:
        await ctx.step.sleep("sleep", datetime.timedelta(seconds=1))
        return "done"

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        state.request_counter += 1

        async def _step_1a() -> int:
            state.step_1a_counter += 1
            return 1

        async def _step_1b() -> int:
            state.step_1b_counter += 1
            return 2

        state.parallel_output = await ctx.group.parallel(
            (
                lambda: ctx.step.invoke("invoke", function=fn_child_async),
                lambda: ctx.step.run("1a", _step_1a),
                lambda: ctx.step.run("1b", _step_1b),
                lambda: ctx.step.send_event(
                    "send", events=inngest.Event(name="noop")
                ),
            )
        )

        async def _step_after() -> None:
            state.step_after_counter += 1

        await ctx.step.run("after", _step_after)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.parallel_output == (
            "done",
            1,
            2,
            [unittest.mock.ANY],
        )
        assert state.step_1a_counter == 1
        assert state.step_1b_counter == 1
        assert state.step_after_counter == 1

        # 7 because we have:
        # - 4 parallel steps
        # - 1 for planning "after" step
        # - 1 for running "after" step
        # - 1 for the final function return
        assert state.request_counter == 7

    fn: list[inngest.Function[typing.Any]]
    if is_sync:
        fn = [fn_sync, fn_child_sync]
    else:
        fn = [fn_async, fn_child_async]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
