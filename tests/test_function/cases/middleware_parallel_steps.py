import inngest
import tests.helper
from inngest._internal import const, execution, middleware_lib

from . import base


class _State(base.BaseState):
    def __init__(self) -> None:
        self.results: list[inngest.TransformOutputResult] = []
        self.messages: list[str] = []


def create(
    client: inngest.Inngest,
    framework: const.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    class _Middleware(inngest.MiddlewareSync):
        def transform_output(
            self,
            result: inngest.TransformOutputResult,
        ) -> None:
            state.results.append(result)

    @client.create_function(
        fn_id=fn_id,
        middleware=[_Middleware],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> str:
        state.run_id = ctx.run_id

        step.parallel(
            (
                lambda: step.run("1.1", lambda: "1.1 (step)"),
                lambda: step.run("1.2", lambda: "1.2 (step)"),
            )
        )

        return "2 (fn)"

    @client.create_function(
        fn_id=fn_id,
        middleware=[_Middleware],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> str:
        state.run_id = ctx.run_id

        await step.parallel(
            (
                lambda: step.run("1.1", lambda: "1.1 (step)"),
                lambda: step.run("1.2", lambda: "1.2 (step)"),
            )
        )

        return "2 (fn)"

    def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        results = sorted(state.results, key=lambda x: str(x.output))

        if len(results) == 4:
            # The last request (the function return) usually happens twice but
            # sometimes only once. This is probably a race condition between the
            # Executor and SDK, so we'll pop the "extra" result if it exists
            results.pop()

        _assert_results(
            results,
            [
                inngest.TransformOutputResult(
                    error=None,
                    output="1.1 (step)",
                    step=middleware_lib.TransformOutputStepInfo(
                        id="1.1",
                        op=execution.Opcode.STEP_RUN,
                        opts=None,
                    ),
                ),
                inngest.TransformOutputResult(
                    error=None,
                    output="1.2 (step)",
                    step=middleware_lib.TransformOutputStepInfo(
                        id="1.2",
                        op=execution.Opcode.STEP_RUN,
                        opts=None,
                    ),
                ),
                inngest.TransformOutputResult(
                    error=None,
                    output="2 (fn)",
                    step=None,
                ),
            ],
        )

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )


def _assert_results(
    actual: list[inngest.TransformOutputResult],
    expected: list[inngest.TransformOutputResult],
) -> None:
    assert len(actual) == len(expected)

    for i, (a, e) in enumerate(zip(actual, expected)):
        assert a.__dict__ == e.__dict__, f"index={i}"
