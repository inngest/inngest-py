import time

import inngest
import tests.helper

from . import base

_TEST_NAME = "cancel"


class _State(base.BaseState):
    is_done: bool = False


def create(
    client: inngest.Inngest,
    framework: str,
) -> base.Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(
            cancel=[
                inngest.Cancel(
                    event=f"{event_name}.cancel",
                    if_exp="event.data.id == async.data.id",
                ),
            ],
            id=_TEST_NAME,
        ),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, run_id: str, step: inngest.Step, **_kwargs: object) -> None:
        state.run_id = run_id

        # Wait a little bit to allow the cancel event to be sent.
        time.sleep(3)

        # The test will need to wait for this function's logic to finish even
        # though it's cancelled. Without this, Tornado will error due to logic
        # still running after the test is done.
        state.is_done = True

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name, data={"id": "foo"}))
        run_id = state.wait_for_run_id()
        client.send(
            inngest.Event(name=f"{event_name}.cancel", data={"id": "foo"})
        )
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.CANCELLED,
        )

        def assert_is_done() -> None:
            assert state.is_done

        base.wait_for(assert_is_done)

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
