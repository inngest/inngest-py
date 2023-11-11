import inngest
import tests.helper

from . import base

_TEST_NAME = "function_args"


class _State(base.BaseState):
    attempt: int | None = None
    event: inngest.Event | None = None
    events: list[inngest.Event] | None = None
    step: inngest.Step | inngest.StepSync | None = None


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        *,
        attempt: int,
        event: inngest.Event,
        events: list[inngest.Event],
        logger: inngest.Logger,
        run_id: str,
        step: inngest.StepSync,
    ) -> None:
        state.attempt = attempt
        state.event = event
        state.events = events
        state.run_id = run_id
        state.step = step

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        *,
        attempt: int,
        event: inngest.Event,
        events: list[inngest.Event],
        logger: inngest.Logger,
        run_id: str,
        step: inngest.Step,
    ) -> None:
        state.attempt = attempt
        state.event = event
        state.events = events
        state.run_id = run_id
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
        assert isinstance(state.step, inngest.Step | inngest.StepSync)

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
