import json
import unittest.mock

import inngest
import tests.helper

from . import base

_TEST_NAME = "non_retriable_error"


class _State(base.BaseState):
    attempt: int = -1


def create(
    client: inngest.Inngest,
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        state.attempt = ctx.attempt
        state.run_id = ctx.run_id

        def step_1() -> None:
            raise inngest.NonRetriableError("foo")

        step.run("step_1", step_1)

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.attempt = ctx.attempt
        state.run_id = ctx.run_id

        def step_1() -> None:
            raise inngest.NonRetriableError("foo")

        await step.run("step_1", step_1)

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()

        def assert_output() -> None:
            run = tests.helper.client.wait_for_run_status(
                run_id,
                tests.helper.RunStatus.FAILED,
            )

            assert run.output is not None
            output = json.loads(run.output)

            assert output == {
                "error": "NonRetriableError",
                "is_internal": False,
                "is_retriable": False,
                "message": "foo",
                "name": "NonRetriableError",
                "stack": unittest.mock.ANY,
            }

        base.wait_for(assert_output)

        assert state.attempt == 0

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
