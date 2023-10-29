from datetime import timedelta

import inngest
from tests import helper

from . import base

_TEST_NAME = "wait_for_event_timeout"


class _State(base.BaseState):
    result: inngest.Event | None | str = "not_set"


def create(
    client: inngest.Inngest,
    framework: str,
) -> base.Case:
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
            timeout=timedelta(seconds=1),
        )

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.COMPLETED)
        assert state.result is None

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
