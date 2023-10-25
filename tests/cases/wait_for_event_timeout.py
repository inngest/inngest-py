import inngest
from tests import helper

from .base import BaseState, Case

_TEST_NAME = "wait_for_event_timeout"


class _State(BaseState):
    result: inngest.Event | None | str = "not_set"


def create(
    client: inngest.Inngest,
    framework: str,
) -> Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME, retries=0),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, run_id: str, step: inngest.Step, **_kwargs: object) -> None:
        state.run_id = run_id

        state.result = step.wait_for_event(
            "wait",
            event=f"{event_name}.fulfill",
            timeout=inngest.Duration.second(1),
        )

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.COMPLETED)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
