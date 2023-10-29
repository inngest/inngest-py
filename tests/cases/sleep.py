from datetime import datetime, timedelta

import inngest
from tests import helper

from . import base

_TEST_NAME = "sleep"


class _State(base.BaseState):
    after_sleep: datetime | None = None
    before_sleep: datetime | None = None

    def is_done(self) -> bool:
        return self.after_sleep is not None and self.before_sleep is not None


def create(client: inngest.Inngest, framework: str) -> base.Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, run_id: str, step: inngest.Step, **_kwargs: object) -> None:
        state.run_id = run_id

        if state.before_sleep is None:
            state.before_sleep = datetime.now()

        step.sleep("zzz", timedelta(seconds=2))

        if state.after_sleep is None:
            state.after_sleep = datetime.now()

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.COMPLETED)

        assert state.after_sleep is not None and state.before_sleep is not None
        assert state.after_sleep - state.before_sleep >= timedelta(seconds=2)

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
