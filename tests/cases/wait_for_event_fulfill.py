import time
from datetime import timedelta

import inngest
from tests import helper

from . import base

_TEST_NAME = "wait_for_event_fulfill"


class _State(base.BaseState):
    result: inngest.Event | None = None


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
            timeout=timedelta(minutes=1),
        )

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()

        # Sleep long enough for the wait_for_event to register.
        time.sleep(0.5)

        client.send(inngest.Event(name=f"{event_name}.fulfill"))
        helper.client.wait_for_run_status(run_id, helper.RunStatus.COMPLETED)

        assert isinstance(state.result, inngest.Event)
        assert state.result.id != ""
        assert state.result.name == f"{event_name}.fulfill"
        assert state.result.ts > 0

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
