"""
We don't officially support returning a Pydantic object from a step. Returning a
Pydantic object fails a type check, however it'll be converted to a dict at
runtime. Users may be relying on this behavior, so it's probably best to avoid
fixing it.

Note that returning a Pydantic object from a function will fail at runtime.
"""

import pydantic

import inngest
import tests.helper

from . import base

_TEST_NAME = "pydantic_output"


class _User(pydantic.BaseModel):
    name: str


class _State(base.BaseState):
    step_output: object = None


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
        tests.helper.client.wait_for_run_status(
            state.wait_for_run_id(),
            tests.helper.RunStatus.COMPLETED,
        )

        user = _User.model_validate(state.step_output)
        assert user.name == "Alice"

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
