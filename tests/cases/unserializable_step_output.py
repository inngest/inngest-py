import inngest
from inngest._internal import errors
from tests import helper

from . import base

_TEST_NAME = "unserializable_step_output"


class _State(base.BaseState):
    error: BaseException | None = None


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
        run_id = state.wait_for_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.FAILED)

        assert isinstance(state.error, errors.UnserializableOutput)
        assert str(state.error) == "Object of type Foo is not JSON serializable"

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
