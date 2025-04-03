"""
Ensure step and function output is encrypted and decrypted correctly
"""

import json

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import remote_state_middleware

from . import base


class _State(base.BaseState):
    event: inngest.Event
    events: list[inngest.Event]


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()
    driver = remote_state_middleware.InMemoryDriver()

    @client.create_function(
        fn_id=fn_id,
        middleware=[
            remote_state_middleware.RemoteStateMiddleware.factory(driver)
        ],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> str:
        state.run_id = ctx.run_id

        def _step() -> str:
            raise Exception("oh no")

        try:
            ctx.step.run("step_1", _step)
        except Exception as e:
            return str(e)

        return "unreachable"

    @client.create_function(
        fn_id=fn_id,
        middleware=[
            remote_state_middleware.RemoteStateMiddleware.factory(driver)
        ],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> str:
        state.run_id = ctx.run_id

        state.run_id = ctx.run_id

        def _step() -> str:
            raise Exception("oh no")

        try:
            await ctx.step.run("step_1", _step)
        except Exception as e:
            return str(e)

        return "unreachable"

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        # Ensure that step_1 output is encrypted and its value is correct
        output = json.loads(
            await test_core.helper.client.get_step_output(
                run_id=run_id,
                step_id="step_1",
            )
        )
        assert isinstance(output, dict)
        assert output.get("data") is None
        error = output.get("error")
        assert isinstance(error, dict)

        # Ensure that the error data was not remotely stored.
        assert driver._marker not in error
        assert error.get("message") == "oh no"

        assert run.output is not None
        assert json.loads(run.output) == "oh no"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
