import inngest

from .base import BaseState, Case, wait_for

_TEST_NAME = "wait_for_event_timeout"


class _State(BaseState):
    result: inngest.Event | None | str = "not_set"

    def is_done(self) -> bool:
        print(self.result)
        return self.result is None


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
        state.result = step.wait_for_event(
            "wait",
            event=f"{event_name}.fulfill",
            timeout=inngest.Duration.second(1),
        )

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        def assertion() -> None:
            assert state.is_done()

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
