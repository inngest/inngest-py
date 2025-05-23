import datetime
import json
import typing
import unittest.mock

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    attempt: typing.Optional[int] = None
    event: typing.Optional[inngest.Event] = None
    events: typing.Optional[list[inngest.Event]] = None
    on_failure_run_id: typing.Optional[str] = None
    step: typing.Union[inngest.Step, inngest.StepSync, None] = None

    async def wait_for_on_failure_run_id(self) -> str:
        def assertion() -> None:
            assert self.on_failure_run_id is not None

        await base.wait_for(assertion, timeout=datetime.timedelta(seconds=10))
        assert self.on_failure_run_id is not None
        return self.on_failure_run_id


class MyError(Exception):
    pass


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    def on_failure_sync(ctx: inngest.ContextSync) -> None:
        state.attempt = ctx.attempt
        state.event = ctx.event
        state.events = ctx.events
        state.on_failure_run_id = ctx.run_id
        state.step = ctx.step

    async def on_failure_async(ctx: inngest.Context) -> None:
        state.attempt = ctx.attempt
        state.event = ctx.event
        state.events = ctx.events
        state.on_failure_run_id = ctx.run_id
        state.step = ctx.step

    @client.create_function(
        fn_id=fn_id,
        on_failure=on_failure_sync,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        raise MyError("intentional failure")

    @client.create_function(
        fn_id=fn_id,
        on_failure=on_failure_async,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        raise MyError("intentional failure")

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(data={"foo": 1}, name=event_name))

        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.FAILED,
        )

        def assert_is_done() -> None:
            assert state.attempt == 0

        await base.wait_for(assert_is_done)

        assert run.output is not None
        output = json.loads(run.output)
        assert output == {
            "code": "unknown",
            "message": "intentional failure",
            "name": "MyError",
            "stack": unittest.mock.ANY,
        }
        stack = output["stack"]
        assert isinstance(stack, str)
        assert stack.startswith("Traceback (most recent call last):")

        # The SDK's internal code doesn't appear in the traceback since the
        # error occurred in user code.
        assert "inngest/_internal" not in stack

        # User code is in the traceback.
        assert 'test_function/cases/on_failure.py", line' in stack

        run_id = await state.wait_for_on_failure_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        # The on_failure handler has a different run ID than the original run.
        assert state.run_id != state.on_failure_run_id

        assert state.attempt == 0
        assert isinstance(state.event, inngest.Event)

        # Assert that the error in the failure event is correct
        assert state.event.data.get("error") == {
            "error": "invalid status code: 500",
            "message": "intentional failure",
            "name": "MyError",
            "stack": unittest.mock.ANY,
        }
        assert state.event.data["function_id"] == fn_sync.id
        assert state.event.data["run_id"] == state.run_id

        # The original event should be in the failure event data
        event = inngest.Event.from_raw(state.event.data["event"])
        assert not isinstance(event, Exception)
        assert event.data == {"foo": 1}
        assert len(event.id) > 0
        assert event.name == event_name
        assert event.ts > 0

        assert isinstance(state.events, list) and len(state.events) == 1
        assert isinstance(state.step, (inngest.Step, inngest.StepSync))

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
