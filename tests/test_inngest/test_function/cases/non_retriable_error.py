import json
import unittest.mock

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    attempt: int = -1


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    @client.create_function(
        fn_id=fn_id,
        retries=1,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.attempt = ctx.attempt
        state.run_id = ctx.run_id

        def step_1() -> None:
            raise inngest.NonRetriableError("foo", quiet=True)

        ctx.step.run("step_1", step_1)

    @client.create_function(
        fn_id=fn_id,
        retries=1,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.attempt = ctx.attempt
        state.run_id = ctx.run_id

        async def step_1() -> None:
            raise inngest.NonRetriableError("foo", quiet=True)

        await ctx.step.run("step_1", step_1)

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()

        async def assert_output() -> None:
            run = await test_core.helper.client.wait_for_run_status(
                run_id,
                test_core.helper.RunStatus.FAILED,
            )

            assert run.output is not None
            output = json.loads(run.output)

            assert output == {
                "code": "non_retriable_error",
                "message": "foo",
                "name": "NonRetriableError",
                "stack": unittest.mock.ANY,
            }

        await base.wait_for(assert_output)

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
