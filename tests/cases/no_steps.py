import inngest
from tests import helper

from . import base

_TEST_NAME = "no_steps"


def create(client: inngest.Inngest, framework: str) -> base.Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = base.BaseState()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, run_id: str, **_kwargs: object) -> None:
        state.run_id = run_id

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.COMPLETED)

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
