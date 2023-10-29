import inngest
from tests import helper

from .base import BaseState, Case, wait_for

_TEST_NAME = "on_failure"


class _State(BaseState):
    attempt: int | None = None
    event: inngest.Event | None = None
    events: list[inngest.Event] | None = None
    on_failure_run_id: str | None = None
    step: inngest.Step | None = None

    def wait_for_on_failure_run_id(self) -> str:
        def assertion() -> None:
            assert self.on_failure_run_id is not None

        wait_for(assertion)
        assert self.on_failure_run_id is not None
        return self.on_failure_run_id


def create(client: inngest.Inngest, framework: str) -> Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    def on_failure(
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
        state.on_failure_run_id = run_id
        state.step = step

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME, on_failure=on_failure, retries=0),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, run_id: str, step: inngest.Step, **_kwargs: object) -> None:
        state.run_id = run_id
        raise Exception("intentional failure")

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        run_id = state.wait_for_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.FAILED)

        run_id = state.wait_for_on_failure_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.COMPLETED)

        # The on_failure handler has a different run ID than the original run.
        assert state.run_id != state.on_failure_run_id

        assert state.attempt == 0
        assert isinstance(state.event, inngest.Event)
        assert isinstance(state.events, list) and len(state.events) == 1
        assert isinstance(state.step, inngest.Step)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
