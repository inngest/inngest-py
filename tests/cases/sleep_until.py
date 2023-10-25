from datetime import datetime, timedelta

import inngest

from .base import BaseState, Case, wait_for

_TEST_NAME = "sleep_until"


class _State(BaseState):
    after_sleep: datetime | None = None
    before_sleep: datetime | None = None

    def is_done(self) -> bool:
        return self.after_sleep is not None and self.before_sleep is not None


def create(client: inngest.Inngest, framework: str) -> Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, step: inngest.Step, **_kwargs: object) -> None:
        if state.before_sleep is None:
            state.before_sleep = datetime.now()

        step.sleep_until("zzz", datetime.now() + timedelta(seconds=2))

        if state.after_sleep is None:
            state.after_sleep = datetime.now()

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        def assertion() -> None:
            assert state.is_done()
            assert (
                state.after_sleep is not None and state.before_sleep is not None
            )
            assert state.after_sleep - state.before_sleep >= timedelta(
                seconds=2
            )

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
