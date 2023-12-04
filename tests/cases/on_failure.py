import json
import unittest.mock

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


class MyError(Exception):
    pass


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    def on_failure_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.attempt = ctx.attempt
        state.event = ctx.event
        state.events = ctx.events
        state.on_failure_run_id = ctx.run_id
        state.step = step

    async def on_failure_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.attempt = ctx.attempt
        state.event = ctx.event
        state.events = ctx.events
        state.on_failure_run_id = ctx.run_id
        state.step = step

    @inngest.create_function(
        fn_id=fn_id,
        on_failure=on_failure_sync,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.run_id = ctx.run_id
        raise MyError("intentional failure")

    @inngest.create_function(
        fn_id=fn_id,
        on_failure=on_failure_async,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id
        raise MyError("intentional failure")

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(data={"foo": 1}, name=event_name))

        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.FAILED,
        )

        def assert_is_done() -> None:
            assert state.attempt == 0

        base.wait_for(assert_is_done)

        assert run.output is not None
        output = json.loads(run.output)
        assert output == {
            "isInternal": False,
            "isRetriable": True,
            "message": "intentional failure",
            "name": "MyError",
            "stack": unittest.mock.ANY,
        }, output
        stack = output["stack"]
        assert isinstance(stack, str)
        assert stack.startswith("Traceback (most recent call last):")

        run_id = state.wait_for_on_failure_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        # The on_failure handler has a different run ID than the original run.
        assert state.run_id != state.on_failure_run_id

        assert state.attempt == 0, state.attempt
        assert isinstance(state.event, inngest.Event)

        # The serialized error
        # Assert that the error in the failure event is correct
        error = state.event.data.get("error")
        assert isinstance(error, dict), error
        assert error.get("isInternal") is False, error
        assert error.get("isRetriable") is True, error
        assert error.get("message") == "intentional failure", error
        assert error.get("name") == "MyError", error
        assert isinstance(error.get("stack"), str), error

        assert state.event.data["function_id"] == fn_id
        assert state.event.data["run_id"] == state.run_id

        # The original event should be in the failure event data
        event = inngest.Event.from_raw(state.event.data["event"])
        assert not isinstance(event, Exception)
        assert event.data == {"foo": 1}, event.data
        assert len(event.id) > 0
        assert event.name == event_name, event.name
        assert event.ts > 0

        assert isinstance(state.events, list) and len(state.events) == 1
        assert isinstance(state.step, inngest.Step | inngest.StepSync)

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
