import logging

import inngest
import test_core.helper
from inngest._internal import server_lib

from . import base


class _State(base.BaseState):
    fn_raise: bool = False
    step_raise: bool = False


class StatefulLogger(logging.Logger):
    """Fake logger that stores calls to its methods. We can use this to assert that
    logger methods are properly called (e.g. no duplicates).
    """

    def __init__(self) -> None:
        super().__init__("test")
        self.info_calls: list[object] = []

    def info(self, msg: object, *args: object, **kwargs: object) -> None:
        self.info_calls.append(msg)


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = test_name
    state = _State()

    _logger = StatefulLogger()

    @client.create_function(
        fn_id=fn_id,
        retries=1,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        ctx.logger.info("function start")
        state.run_id = ctx.run_id

        def step_1() -> None:
            ctx.logger.info("step_1")

        ctx.step.run("step_1", step_1)

        ctx.logger.info("log before function-level raise")
        if state.fn_raise is False:
            state.fn_raise = True
            raise inngest.RetryAfterError("", 1000, quiet=True)

        def step_2() -> None:
            ctx.logger.info("step_2")

        ctx.step.run("step_2", step_2)

        ctx.logger.info("log before step-level raise")

        def step_3() -> None:
            if state.step_raise is False:
                state.step_raise = True
                raise inngest.RetryAfterError("", 1000, quiet=True)

        ctx.step.run("step_3", step_3)

        ctx.logger.info("function end")

    @client.create_function(
        fn_id=fn_id,
        retries=1,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        ctx.logger.info("function start")
        state.run_id = ctx.run_id

        async def step_1() -> None:
            ctx.logger.info("step_1")

        await ctx.step.run("step_1", step_1)

        ctx.logger.info("log before function-level raise")
        if state.fn_raise is False:
            state.fn_raise = True
            raise inngest.RetryAfterError("", 1000, quiet=True)

        async def step_2() -> None:
            ctx.logger.info("step_2")

        await ctx.step.run("step_2", step_2)

        ctx.logger.info("log before step-level raise")

        async def step_3() -> None:
            if state.step_raise is False:
                state.step_raise = True
                raise inngest.RetryAfterError("", 1000, quiet=True)

        await ctx.step.run("step_3", step_3)

        ctx.logger.info("function end")

    async def run_test(self: base.TestClass) -> None:
        self.client.set_logger(_logger)
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        assert _logger.info_calls == [
            "function start",
            "step_1",
            "log before function-level raise",
            "log before function-level raise",
            "step_2",
            "log before step-level raise",
            "log before step-level raise",
            "function end",
        ]

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
