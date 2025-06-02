"""
Steps error if they return a Pydantic object without specifying a type adapter.
"""

import json

import inngest
import pydantic
import test_core.helper
from inngest._internal import server_lib

from . import base


class _User(pydantic.BaseModel):
    name: str


class _State(base.BaseState):
    step_output: object = None


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
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id
        state.step_output = ctx.step.run(
            "a",
            lambda: _User(name="Alice"),
        )

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id
        state.step_output = await ctx.step.run(
            "a",
            base.asyncify(lambda: _User(name="Alice")),
        )

    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run = await test_core.helper.client.wait_for_run_status(
            await state.wait_for_run_id(),
            test_core.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)
        assert isinstance(output, dict)
        assert output["message"] == '"a" returned unserializable data'
        assert output["name"] == "OutputUnserializableError"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
