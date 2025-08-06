import asyncio
import datetime
import time
import typing

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)

    class _State(base.BaseState):
        request_counter = 0
        step_order: list[str] = []  # noqa: RUF012

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

        def _step_a1() -> None:
            state.step_order.append("a.1")

        def _step_a2() -> None:
            state.step_order.append("a.2")

        def _step_b1() -> None:
            time.sleep(2)
            state.step_order.append("b.1")

        def _step_b2() -> None:
            time.sleep(2)
            state.step_order.append("b.2")

        def fast_group() -> None:
            ctx.step.run("a.1", _step_a1)
            ctx.step.run("a.2", _step_a2)

        def slow_group() -> None:
            ctx.step.run("b.1", _step_b1)
            ctx.step.run("b.2", _step_b2)

        ctx.group.parallel(
            (fast_group, slow_group),
            parallel_mode=inngest.ParallelMode.RACE,
        )

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

        async def _step_a1() -> None:
            state.step_order.append("a.1")

        async def _step_a2() -> None:
            state.step_order.append("a.2")

        async def _step_b1() -> None:
            await asyncio.sleep(2)
            state.step_order.append("b.1")

        async def _step_b2() -> None:
            await asyncio.sleep(2)
            state.step_order.append("b.2")

        async def fast_group() -> None:
            await ctx.step.run("a.1", _step_a1)
            await ctx.step.run("a.2", _step_a2)

        async def slow_group() -> None:
            await ctx.step.run("b.1", _step_b1)
            await ctx.step.run("b.2", _step_b2)

        await ctx.group.parallel(
            (fast_group, slow_group),
            parallel_mode=inngest.ParallelMode.RACE,
        )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.step_order == ["a.1", "a.2", "b.1", "b.2"]

        # 9 because we have:
        # - 1 initial parallel plan (plan [a.1, a.2])
        # - 4 parallel steps
        # - 4 discovery requests (after each parallel step)
        assert state.request_counter == 9

    fn: list[inngest.Function[typing.Any]]
    if is_sync:
        fn = [fn_sync, fn_child_sync]
    else:
        fn = [fn_async, fn_child_async]

    # Skip these frameworks because their tests don't run in multi-threaded mode
    if framework in [
        server_lib.Framework.DIGITAL_OCEAN,
        server_lib.Framework.DJANGO,
    ]:
        fn = []

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
