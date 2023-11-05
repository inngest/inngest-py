import json

import inngest
import tests.helper

from . import base

_TEST_NAME = "unserializable_step_output"


class _State(base.BaseState):
    error: BaseException | None = None


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    @inngest.create_function(
        fn_id=test_name,
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

        class Foo:
            pass

        def step_1() -> Foo:
            return Foo()

        try:
            step.run(
                "step_1",
                step_1,  # type: ignore
            )
        except BaseException as err:
            state.error = err
            raise

    @inngest.create_function(
        fn_id=test_name,
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

        class Foo:
            pass

        async def step_1() -> Foo:
            return Foo()

        await step.run("step_1", step_1)  # type: ignore

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
            "message": '"step_1" returned unserializable data',
            "name": "UnserializableOutputError",
        }, output

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
