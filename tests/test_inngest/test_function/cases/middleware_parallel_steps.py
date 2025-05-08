"""
NOTE: This test is flaky because of inherent race behavior in parallel steps.
Sometimes the "converge" step is targeted before the other parallel step
finishes, causing the assertion to fail. This is not considered a bug. The
flakiness should be fixed when we finish parallelism improvements.
"""

import inngest
import pytest
import test_core.helper
from inngest._internal import middleware_lib, server_lib

from . import base


class _State(base.BaseState):
    def __init__(self) -> None:
        self.results: list[inngest.TransformOutputResult] = []
        self.messages: list[str] = []


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
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
    def fn_sync(ctx: inngest.ContextSync) -> str:
        state.run_id = ctx.run_id

        ctx.group.parallel(
            (
                lambda: ctx.step.run("1.1", lambda: "1.1 (step)"),
                lambda: ctx.step.run("1.2", lambda: "1.2 (step)"),
            )
        )

        # Only necessary because of a parallel step bug within the Inngest
        # server. If a function ends with parallel steps then sometimes a
        # discovery step happens after the run is finalized (and therefore its
        # state was deleted).
        ctx.step.run("converge", lambda: None)

        return "2 (fn)"

    @client.create_function(
        fn_id=fn_id,
        middleware=[_Middleware],
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> str:
        state.run_id = ctx.run_id

        await ctx.group.parallel(
            (
                lambda: ctx.step.run("1.1", lambda: "1.1 (step)"),
                lambda: ctx.step.run("1.2", lambda: "1.2 (step)"),
            )
        )

        # Only necessary because of a parallel step bug within the Inngest
        # server. If a function ends with parallel steps then sometimes a
        # discovery step happens after the run is finalized (and therefore its
        # state was deleted).
        await ctx.step.run("converge", lambda: None)

        return "2 (fn)"

    # TODO: Delete this decorator when we implement parallelism improvements.
    @pytest.mark.xfail
    async def run_test(self: base.TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        results = sorted(state.results, key=lambda x: str(x.output))

        _assert_results(
            results,
            [
                inngest.TransformOutputResult(
                    error=None,
                    output="1.1 (step)",
                    step=middleware_lib.TransformOutputStepInfo(
                        id="1.1",
                        op=server_lib.Opcode.STEP_RUN,
                        opts=None,
                    ),
                ),
                inngest.TransformOutputResult(
                    error=None,
                    output="1.2 (step)",
                    step=middleware_lib.TransformOutputStepInfo(
                        id="1.2",
                        op=server_lib.Opcode.STEP_RUN,
                        opts=None,
                    ),
                ),
                inngest.TransformOutputResult(
                    error=None,
                    output="2 (fn)",
                    step=None,
                ),
                inngest.TransformOutputResult(
                    error=None,
                    output=None,
                    step=middleware_lib.TransformOutputStepInfo(
                        id="converge",
                        op=server_lib.Opcode.PLANNED,
                        opts=None,
                    ),
                ),
                inngest.TransformOutputResult(
                    error=None,
                    output=None,
                    step=middleware_lib.TransformOutputStepInfo(
                        id="converge",
                        op=server_lib.Opcode.PLANNED,
                        opts=None,
                    ),
                ),
                inngest.TransformOutputResult(
                    error=None,
                    output=None,
                    step=middleware_lib.TransformOutputStepInfo(
                        id="converge",
                        op=server_lib.Opcode.STEP_RUN,
                        opts=None,
                    ),
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
    for i, (a, e) in enumerate(zip(actual, expected)):
        assert a.__dict__ == e.__dict__, f"index={i}"

    assert len(actual) == len(expected)
