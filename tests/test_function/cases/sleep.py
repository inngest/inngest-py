import datetime
import typing

import inngest
import tests.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    after_sleep: typing.Optional[datetime.datetime] = None
    before_sleep: typing.Optional[datetime.datetime] = None

    def is_done(self) -> bool:
        return self.after_sleep is not None and self.before_sleep is not None


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
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        if state.before_sleep is None:
            state.before_sleep = datetime.datetime.now()

        step.sleep("zzz", datetime.timedelta(seconds=2))

        if state.after_sleep is None:
            state.after_sleep = datetime.datetime.now()

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id

        if state.before_sleep is None:
            state.before_sleep = datetime.datetime.now()

        await step.sleep("zzz", datetime.timedelta(seconds=2))

        if state.after_sleep is None:
            state.after_sleep = datetime.datetime.now()

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.after_sleep is not None and state.before_sleep is not None
        assert state.after_sleep - state.before_sleep >= datetime.timedelta(
            seconds=2
        )

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
