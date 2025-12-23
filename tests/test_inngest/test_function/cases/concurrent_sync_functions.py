import dataclasses
import time
import typing

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


@dataclasses.dataclass
class _State(base.BaseState):
    run_ids: set[str]


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = test_name
    state = _State(run_ids=set())

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_ids.add(ctx.run_id)

        # This will loop forever if the function run is blocking the event
        # loop, causing the test to timeout.
        while True:
            if len(state.run_ids) == 2:
                break
            time.sleep(0.1)

    async def run_test(self: base.TestClass) -> None:
        # Trigger the function twice.
        self.client.send_sync(
            [
                inngest.Event(name=event_name),
                inngest.Event(name=event_name),
            ]
        )

        # Wait for both runs to start.
        def assert_runs() -> None:
            assert len(state.run_ids) == 2

        await test_core.wait_for(assert_runs)

        i = iter(state.run_ids)
        run_1_id = next(i)
        run_2_id = next(i)

        # Wait for both runs to complete. This will only happen if the functions
        # don't block each other.
        await test_core.helper.client.wait_for_run_status(
            run_1_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        await test_core.helper.client.wait_for_run_status(
            run_2_id,
            test_core.helper.RunStatus.COMPLETED,
        )

    fn: list[inngest.Function[typing.Any]]
    if is_sync:
        # This test is only relevant for async frameworks. Set fn to an empty
        # list cause this test to skip for sync frameworks.
        fn = []
    else:
        fn = [fn_sync]

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
