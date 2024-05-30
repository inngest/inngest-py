"""
We don't support returning Pydantic models in steps or functions. This may
change in the future.
"""

import json

import pydantic

import inngest
import tests.helper
from inngest._internal import const

from . import base

_TEST_NAME = "pydantic_output"


class _User(pydantic.BaseModel):
    name: str


class _State(base.BaseState):
    step_output: object = None


def create(
    client: inngest.Inngest,
    framework: const.Framework,
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
        state.run_id = ctx.run_id
        state.step_output = step.run(
            "a",
            lambda: _User(name="Alice"),  # type: ignore
        )

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        state.run_id = ctx.run_id
        state.step_output = await step.run(
            "a",
            lambda: _User(name="Alice"),  # type: ignore
        )

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run = tests.helper.client.wait_for_run_status(
            state.wait_for_run_id(),
            tests.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        assert json.loads(run.output) == {
            "code": "output_unserializable",
            "message": '"a" returned unserializable data',
            "name": "OutputUnserializableError",
        }

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
