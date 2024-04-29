import logging

import inngest
import tests.helper

from . import base

_TEST_NAME = "logger"


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
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = base.BaseState()

    _logger = StatefulLogger()

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        ctx.logger.info("function start")
        state.run_id = ctx.run_id

        def _first_step() -> None:
            ctx.logger.info("first_step")

        step.run("first_step", _first_step)

        ctx.logger.info("between steps")

        def _second_step() -> None:
            ctx.logger.info("second_step")

        step.run("second_step", _second_step)
        ctx.logger.info("function end")

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> None:
        ctx.logger.info("function start")
        state.run_id = ctx.run_id

        def _first_step() -> None:
            ctx.logger.info("first_step")

        await step.run("first_step", _first_step)

        ctx.logger.info("between steps")

        def _second_step() -> None:
            ctx.logger.info("second_step")

        await step.run("second_step", _second_step)
        ctx.logger.info("function end")

    def run_test(self: base.TestClass) -> None:
        self.client.set_logger(_logger)
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        assert _logger.info_calls == [
            "function start",
            "first_step",
            "between steps",
            "second_step",
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
