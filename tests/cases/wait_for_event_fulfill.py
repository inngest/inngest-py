import time

import inngest

from .base import BaseState, Case, wait_for

_TEST_NAME = "wait_for_event_fulfill"


class _State(BaseState):
    is_started = False
    result: inngest.Event | None = None

    def is_done(self) -> bool:
        return self.result is not None


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
    def fn(*, step: inngest.Step, **_kwargs: object) -> None:
        state.is_started = True

        state.result = step.wait_for_event(
            "wait",
            event=f"{event_name}.fulfill",
            timeout=inngest.Duration.minute(1),
        )

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        def assert_started() -> None:
            assert state.is_started is True
            time.sleep(0.5)

        wait_for(assert_started)

        client.send(inngest.Event(name=f"{event_name}.fulfill"))

        def assertion() -> None:
            assert state.is_done()
            assert isinstance(state.result, inngest.Event)
            assert state.result.id != ""
            assert state.result.name == f"{event_name}.fulfill"
            assert state.result.ts > 0

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
