"""
Wait for event times out if its expression isn't matched
"""

import datetime
import time
import typing

import inngest
import tests.helper
from inngest._internal import const

from . import base


class _State(base.BaseState):
    result: typing.Union[inngest.Event, None, str] = "not_set"


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
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id

        state.result = step.wait_for_event(
            "wait",
            event=f"{event_name}.fulfill",
            if_exp="event.data.id == async.data.id",
            timeout=datetime.timedelta(seconds=1),
        )

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

        state.result = await step.wait_for_event(
            "wait",
            event=f"{event_name}.fulfill",
            if_exp="event.data.id == async.data.id",
            timeout=datetime.timedelta(seconds=1),
        )

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(
            inngest.Event(
                data={"id": 123},
                name=event_name,
            )
        )
        run_id = state.wait_for_run_id()

        # Sleep long enough for the wait_for_event to register.
        time.sleep(0.5)

        self.client.send_sync(
            inngest.Event(
                data={"id": 456},
                name=f"{event_name}.fulfill",
            )
        )
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.result is None

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
