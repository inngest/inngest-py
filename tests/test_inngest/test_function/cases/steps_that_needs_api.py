"""
Return total step output so large that it can't be included in the request sent
from the Executor to the SDK. The SDK will need to fetch the memoized step data
from the API
"""

import functools

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    def __init__(self) -> None:
        super().__init__()
        self.step_counters: dict[str, int] = {}


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
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id

        # Create a large enough total step output to force the SDK to fetch the
        # memoized step data from the API
        for i in range(10):

            def fn(step_id: str) -> str:
                state.step_counters[step_id] = (
                    state.step_counters.get(step_id, 0) + 1
                )
                return "a" * 1024 * 1024

            step_id = f"step_{i}"
            ctx.step.run(step_id, functools.partial(fn, step_id))

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        # Create a large enough total step output to force the SDK to fetch the
        # memoized step data from the API
        for i in range(10):

            def fn(step_id: str) -> str:
                state.step_counters[step_id] = (
                    state.step_counters.get(step_id, 0) + 1
                )
                return "a" * 1024 * 1024

            step_id = f"step_{i}"
            await ctx.step.run(
                step_id,
                base.asyncify(functools.partial(fn, step_id)),
            )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        for counter in state.step_counters.values():
            assert counter == 1

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
