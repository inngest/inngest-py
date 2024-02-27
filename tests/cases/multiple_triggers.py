import asyncio
from dataclasses import dataclass

import inngest
import tests.helper

from . import base

_TEST_NAME = "multiple_triggers"


@dataclass
class StateAndEvent:
    state: base.BaseState
    event_name: str


def create(client: inngest.Inngest, framework: str, is_sync: bool) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
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
        async def trigger_event_and_wait(state_event: StateAndEvent) -> None:
            await self.client.send(inngest.Event(name=state_event.event_name))
            run_id = state_event.state.wait_for_run_id()
            tests.helper.client.wait_for_run_status(
                run_id, tests.helper.RunStatus.COMPLETED
            )

        async def run_all() -> None:
            await asyncio.gather(
                *(trigger_event_and_wait(se) for se in states_events)
            )

        asyncio.run(run_all())

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
