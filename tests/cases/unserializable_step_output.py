import json

import inngest
import tests.helper

from . import base

_TEST_NAME = "unserializable_step_output"


class _State(base.BaseState):
    error: BaseException | None = None


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

        class Foo:
            pass

        def step_1() -> Foo:
            return Foo()

        try:
            step.run("step_1", step_1)
        except BaseException as err:
            state.error = err
            raise

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

        class Foo:
            pass

        async def step_1() -> Foo:
            return Foo()

        await step.run("step_1", step_1)

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        run = tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.FAILED,
        )

        assert run.output is not None
        output = json.loads(run.output)

        assert output == {
            "code": "unserializable_output",
            "error": "invalid status code: 500",
            "message": '"step_1" returned unserializable data',
            "name": "UnserializableOutputError",
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
