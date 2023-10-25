import inngest

from .base import BaseState, Case, wait_for

_TEST_NAME = "no_steps"


class _State(BaseState):
    counter = 0

    def is_done(self) -> bool:
        return self.counter == 1


def create(client: inngest.Inngest, framework: str) -> Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(**_kwargs: object) -> None:
        state.counter += 1

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
