"""
Send a batch so large that it can't be included in the request sent from the
Executor to the SDK. The SDK will need to fetch the batch from the API

TODO: Improve this test. It's kinda testing the use_api field in a roundabout
way. We should have a simpler test that just ensures the SDK reaches out to the
API when use_api is true.
"""

import datetime

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    events: list[inngest.Event] | None = None


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
        batch_events=inngest.Batch(
            max_size=8,
            timeout=datetime.timedelta(seconds=10),
        ),
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        state.events = ctx.events

    @client.create_function(
        batch_events=inngest.Batch(
            max_size=8,
            timeout=datetime.timedelta(seconds=10),
        ),
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        state.events = ctx.events

    async def run_test(self: base.TestClass) -> None:
        # Send a large (in terms of bytes, not event count) enough batch to
        # ensure that the SDK needs to fetch the batch from the API
        events: list[inngest.Event] = []
        for _ in range(8):
            events.append(
                inngest.Event(
                    data={"msg": "a" * 1024 * 1024},
                    name=event_name,
                )
            )
        self.client.send_sync(events)

        run_id = await state.wait_for_run_id(
            timeout=datetime.timedelta(seconds=10)
        )
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.events is not None
        assert len(state.events) == 8

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
