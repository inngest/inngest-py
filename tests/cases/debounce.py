import datetime

import inngest
import tests.helper

from . import base

_TEST_NAME = "debounce"


class _State(base.BaseState):
    run_count: int = 0


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    @inngest.create_function(
        debounce=inngest.Debounce(
            period=datetime.timedelta(seconds=1),
        ),
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        *, run_id: str, step: inngest.StepSync, **_kwargs: object
    ) -> None:
        state.run_count += 1
        state.run_id = run_id

    @inngest.create_function(
        debounce=inngest.Debounce(
            period=datetime.timedelta(seconds=3),
        ),
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        *, run_id: str, step: inngest.Step, **_kwargs: object
    ) -> None:
        state.run_count += 1
        state.run_id = run_id

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id(timeout=datetime.timedelta(seconds=10))
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )
        assert state.run_count == 1, f"Expected 1 run but got {state.run_count}"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=test_name,
    )
