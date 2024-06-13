"""
Send a batch so large that it can't be included in the request sent from the
Executor to the SDK. The SDK will need to fetch the batch from the API
"""

import datetime
import typing

import inngest
import tests.helper
from inngest._internal import const

from . import base


class _State(base.BaseState):
    events: typing.Optional[list[inngest.Event]] = None


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
        batch_events=inngest.Batch(
            max_size=50,
            timeout=datetime.timedelta(seconds=10),
        ),
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id
        state.events = ctx.events

    @client.create_function(
        batch_events=inngest.Batch(
            max_size=50,
            timeout=datetime.timedelta(seconds=10),
        ),
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id
        state.events = ctx.events

    async def run_test(self: base.TestClass) -> None:
        # Send a large (in terms of bytes, not event count) enough batch to
        # ensure that the SDK needs to fetch the batch from the API
        events = []
        for _ in range(50):
            events.append(
                inngest.Event(
                    data={"msg": "a" * 1024 * 1024},
                    name=event_name,
                )
            )
        self.client.send_sync(events)

        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.events is not None
        assert len(state.events) == 50

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
