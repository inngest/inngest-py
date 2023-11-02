import logging

import inngest
import tests.helper

from . import base

_TEST_NAME = "on_failure"


class _State(base.BaseState):
    attempt: int | None = None
    event: inngest.Event | None = None
    events: list[inngest.Event] | None = None
    on_failure_run_id: str | None = None
    step: inngest.Step | inngest.StepSync | None = None

    def wait_for_on_failure_run_id(self) -> str:
        def assertion() -> None:
            assert self.on_failure_run_id is not None

        base.wait_for(assertion)
        assert self.on_failure_run_id is not None
        return self.on_failure_run_id


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    def on_failure_sync(
        *,
        attempt: int,
        event: inngest.Event,
        events: list[inngest.Event],
        logger: logging.Logger,
        run_id: str,
        step: inngest.StepSync,
    ) -> None:
        state.attempt = attempt
        state.event = event
        state.events = events
        state.on_failure_run_id = run_id
        state.step = step

    async def on_failure_async(
        *,
        attempt: int,
        event: inngest.Event,
        events: list[inngest.Event],
        logger: logging.Logger,
        run_id: str,
        step: inngest.Step,
    ) -> None:
        state.attempt = attempt
        state.event = event
        state.events = events
        state.on_failure_run_id = run_id
        state.step = step

    @inngest.create_function(
        fn_id=test_name,
        on_failure=on_failure_sync,
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
        raise Exception("intentional failure")

    @inngest.create_function(
        fn_id=test_name,
        on_failure=on_failure_async,
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
        raise Exception("intentional failure")

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.FAILED,
        )

        run_id = state.wait_for_on_failure_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        # The on_failure handler has a different run ID than the original run.
        assert state.run_id != state.on_failure_run_id

        assert state.attempt == 0
        assert isinstance(state.event, inngest.Event)
        assert isinstance(state.events, list) and len(state.events) == 1
        assert isinstance(state.step, (inngest.Step, inngest.StepSync))

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
