from dataclasses import dataclass

import inngest
import tests.helper
from inngest._internal import const

from . import base


@dataclass
class StateAndEvent:
    state: base.BaseState
    event_name: str


def create(
    client: inngest.Inngest,
    framework: const.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    fn_id = base.create_fn_id(test_name)

    states_events = [
        StateAndEvent(
            base.BaseState(),
            base.create_event_name(framework, f"{test_name}_1"),
        ),
        StateAndEvent(
            base.BaseState(),
            base.create_event_name(framework, f"{test_name}_2"),
        ),
    ]

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=[
            inngest.TriggerEvent(event=se.event_name) for se in states_events
        ],
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        for state_event in states_events:
            if ctx.event.name == state_event.event_name:
                state_event.state.run_id = ctx.run_id
                break

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=[
            inngest.TriggerEvent(event=se.event_name) for se in states_events
        ],
    )
    async def fn_async(ctx: inngest.Context, step: inngest.Step) -> None:
        for state_event in states_events:
            if ctx.event.name == state_event.event_name:
                state_event.state.run_id = ctx.run_id
                break

    def run_test(self: base.TestClass) -> None:
        def trigger_event_and_wait(state_event: StateAndEvent) -> None:
            self.client.send_sync(inngest.Event(name=state_event.event_name))
            run_id = state_event.state.wait_for_run_id()
            tests.helper.client.wait_for_run_status(
                run_id, tests.helper.RunStatus.COMPLETED
            )

        for se in states_events:
            trigger_event_and_wait(se)

        assert all(se.state.run_id for se in states_events)
        assert len(set(se.state.run_id for se in states_events)) == len(
            states_events
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
