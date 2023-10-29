import datetime

import inngest
import tests.helper

from . import base

_TEST_NAME = "debounce"


class _State(base.BaseState):
    run_count: int = 0


def create(
    client: inngest.Inngest,
    framework: str,
) -> base.Case:
    event_name = f"{framework}/{_TEST_NAME}"
    state = _State()

    @inngest.create_function(
        inngest.FunctionOpts(
            debounce=inngest.Debounce(
                period=datetime.timedelta(seconds=1),
            ),
            id=_TEST_NAME,
        ),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, run_id: str, step: inngest.Step, **_kwargs: object) -> None:
        state.run_count += 1
        state.run_id = run_id

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))
        client.send(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id(timeout=datetime.timedelta(seconds=10))
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )
        assert state.run_count == 1

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=_TEST_NAME,
    )
