import datetime
import time

import inngest
import tests.helper

from . import base

_TEST_NAME = "wait_for_event_fulfill"


class _State(base.BaseState):
    result: inngest.Event | None = None


def create(
    client: inngest.Inngest,
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    @inngest.create_function_sync(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        *,
        run_id: str,
        step: inngest.StepSync,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        state.result = step.wait_for_event(
            "wait",
            event=f"{event_name}.fulfill",
            timeout=datetime.timedelta(minutes=1),
        )

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        *,
        run_id: str,
        step: inngest.Step,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        state.result = await step.wait_for_event(
            "wait",
            event=f"{event_name}.fulfill",
            timeout=datetime.timedelta(minutes=1),
        )

    def run_test(_self: object) -> None:
        client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()

        # Sleep long enough for the wait_for_event to register.
        time.sleep(0.5)

        client.send_sync(inngest.Event(name=f"{event_name}.fulfill"))
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert isinstance(state.result, inngest.Event)
        assert state.result.id != ""
        assert state.result.name == f"{event_name}.fulfill"
        assert state.result.ts > 0

    fn: inngest.Function | inngest.FunctionSync
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
