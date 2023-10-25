import inngest

from .base import BaseState, Case, wait_for

_TEST_NAME = "function_args"


class _State(BaseState):
    attempt: int | None = None
    event: inngest.Event | None = None
    events: list[inngest.Event] | None = None
    run_id: str | None = None
    step: inngest.Step | None = None

    def is_done(self) -> bool:
        return self.attempt is not None


def create(client: inngest.Inngest, framework: str) -> Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(
        *,
        attempt: int,
        event: inngest.Event,
        events: list[inngest.Event],
        run_id: str,
        step: inngest.Step,
    ) -> None:
        state.attempt = attempt
        state.event = event
        state.events = events
        state.run_id = run_id
        state.step = step

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        def assertion() -> None:
            assert state.is_done()
            assert state.attempt == 0
            assert isinstance(state.event, inngest.Event)
            assert isinstance(state.events, list) and len(state.events) == 1
            assert state.run_id != ""
            assert isinstance(state.step, inngest.Step)

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
