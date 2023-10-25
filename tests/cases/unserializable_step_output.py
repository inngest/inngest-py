import inngest
from inngest._internal.errors import UnserializableOutput

from .base import BaseState, Case, wait_for

_TEST_NAME = "unserializable_step_output"


class _State(BaseState):
    error: BaseException | None = None

    def is_done(self) -> bool:
        return self.error is not None


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
        class Foo:
            pass

        def step_1() -> Foo:
            return Foo()

        try:
            step.run("step_1", step_1)
        except BaseException as err:
            state.error = err
            raise

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        def assertion() -> None:
            assert state.is_done()
            assert isinstance(state.error, UnserializableOutput)
            assert (
                str(state.error)
                == "Object of type Foo is not JSON serializable"
            )

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
