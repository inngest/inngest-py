import typing

import inngest
import tests.helper
from inngest._internal import const

from . import base


class _State(base.BaseState):
    attempt: typing.Optional[int] = None
    event: typing.Optional[inngest.Event] = None
    events: typing.Optional[list[inngest.Event]] = None
    step: typing.Union[inngest.Step, inngest.StepSync, None] = None


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
        state.attempt = ctx.attempt
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id
        state.step = step

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.attempt = ctx.attempt
        state.event = ctx.event
        state.events = ctx.events
        state.run_id = ctx.run_id
        state.step = step

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert state.attempt == 0
        assert isinstance(state.event, inngest.Event)
        assert isinstance(state.events, list) and len(state.events) == 1
        assert isinstance(state.step, (inngest.Step, inngest.StepSync))

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
