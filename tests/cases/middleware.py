import logging
import unittest.mock

import inngest
import tests.helper

# TODO: Remove when middleware is ready for external use.
from inngest._internal import middleware_lib

from . import base

_TEST_NAME = "middleware"


class _State(base.BaseState):
    call_list: list[str] = []


def create(
    framework: str,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(_TEST_NAME, is_sync)
    event_name = base.create_event_name(framework, test_name, is_sync)
    state = _State()

    _logger = unittest.mock.Mock()

    middleware: middleware_lib.Middleware | middleware_lib.MiddlewareSync
    if is_sync:

        class _MiddlewareSync(middleware_lib.MiddlewareSync):
            def after_run_execution(self) -> None:
                state.call_list.append("after_run_execution")

            def before_response(self) -> None:
                state.call_list.append("before_response")

            def before_run_execution(self) -> None:
                state.call_list.append("before_run_execution")

            def transform_input(self) -> inngest.CallInputTransform:
                state.call_list.append("transform_input")
                return inngest.CallInputTransform(logger=_logger)

        middleware = _MiddlewareSync()

    else:

        class _MiddlewareAsync(middleware_lib.Middleware):
            async def after_run_execution(self) -> None:
                state.call_list.append("after_run_execution")

            async def before_response(self) -> None:
                state.call_list.append("before_response")

            async def before_run_execution(self) -> None:
                state.call_list.append("before_run_execution")

            async def transform_input(self) -> inngest.CallInputTransform:
                state.call_list.append("transform_input")
                return inngest.CallInputTransform(logger=_logger)

        middleware = _MiddlewareAsync()

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(
        *,
        logger: logging.Logger,
        step: inngest.StepSync,
        run_id: str,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        def _first_step() -> None:
            logger.info("first_step")

        step.run("first_step", _first_step)

        def _second_step() -> None:
            logger.info("second_step")

        step.run("second_step", _second_step)

    @inngest.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(
        *,
        logger: logging.Logger,
        step: inngest.Step,
        run_id: str,
        **_kwargs: object,
    ) -> None:
        state.run_id = run_id

        def _first_step() -> None:
            logger.info("first_step")

        await step.run("first_step", _first_step)

        def _second_step() -> None:
            logger.info("second_step")

        await step.run("second_step", _second_step)

    def run_test(self: base.TestClass) -> None:
        self.client.middleware.add(middleware)
        self.client.send_sync(inngest.Event(name=event_name))
        run_id = state.wait_for_run_id()
        tests.helper.client.wait_for_run_status(
            run_id,
            tests.helper.RunStatus.COMPLETED,
        )

        # Assert that the middleware hooks were called in the correct order
        assert state.call_list == [
            "before_run_execution",
            "transform_input",
            "before_response",  # first_step done
            "transform_input",
            "before_response",  # second_step done
            "transform_input",
            "after_run_execution",
            "before_response",  # Function done
        ]

        # Assert that the middleware was able to transform the input
        _logger.info.assert_any_call("first_step")
        _logger.info.assert_any_call("second_step")

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
