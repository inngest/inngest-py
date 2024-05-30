import datetime

import inngest
import tests.helper
from inngest._internal import const

from . import base


class _State(base.BaseState):
    run_count: int = 0


def create(
    client: inngest.Inngest,
    framework: const.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        debounce=inngest.Debounce(
            period=datetime.timedelta(seconds=2),
        ),
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_count += 1
        state.run_id = ctx.run_id

    @client.create_function(
        debounce=inngest.Debounce(
            period=datetime.timedelta(seconds=2),
        ),
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_count += 1
        state.run_id = ctx.run_id

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(
            [
                inngest.Event(name=event_name),
                inngest.Event(name=event_name),
            ]
        )
        run_id = state.wait_for_run_id(timeout=datetime.timedelta(seconds=10))
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )
        assert state.run_count == 1

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
