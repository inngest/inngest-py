import inngest
from tests import helper

from . import base

_TEST_NAME = "two_steps"


class _State(base.BaseState):
    step_1_counter = 0
    step_2_counter = 0


def create(client: inngest.Inngest, framework: str) -> base.Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(id=_TEST_NAME),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, run_id: str, step: inngest.Step, **_kwargs: object) -> None:
        state.run_id = run_id

        def step_1() -> str:
            state.step_1_counter += 1
            return "hi"

        step.run("step_1", step_1)

        def step_2() -> None:
            state.step_2_counter += 1

        step.run("step_2", step_2)

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        helper.client.wait_for_run_status(run_id, helper.RunStatus.COMPLETED)

        assert state.step_1_counter == 1
        assert state.step_2_counter == 1

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
