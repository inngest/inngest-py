import dataclasses
import inspect
import logging
import typing

from . import errors, execution, result, transforms

BlankHook = typing.Callable[[], typing.Awaitable[None] | None]


@dataclasses.dataclass
class CallInputTransform:
    logger: logging.Logger | None = None


class Middleware:
    async def after_run_execution(self) -> None:
        """
        After a function run is done executing. Called once per run
        regardless of the number of steps. Will still be called if the run
        failed.
        """

        return None

    async def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """

        return None

    async def before_run_execution(self) -> None:
        """
        Before a function run starts executing. Called once per run
        regardless of the number of steps.
        """

        return None

    async def transform_input(self) -> CallInputTransform:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """

        return CallInputTransform()


class MiddlewareSync:
    def after_run_execution(self) -> None:
        """
        After a function run is done executing. Called once per run
        regardless of the number of steps. Will still be called if the run
        failed.
        """

        return None

    def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """

        return None

    def before_run_execution(self) -> None:
        """
        Before a function run starts executing. Called once per run
        regardless of the number of steps.
        """

        return None

    def transform_input(self) -> CallInputTransform:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """

        return CallInputTransform()


_mismatched_sync = errors.MismatchedSync(
    "encountered async middleware in non-async context"
)


class MiddlewareManager:
    def __init__(
        self,
        middleware: list[Middleware | MiddlewareSync],
    ):
        self._middleware = middleware

    async def after_run_execution(self) -> None:
        for m in self._middleware:
            await transforms.maybe_await(m.after_run_execution())

    def after_run_execution_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.after_run_execution):
                return result.Err(_mismatched_sync)
            m.after_run_execution()
        return result.Ok(None)

    async def before_response(self) -> None:
        for m in self._middleware:
            await transforms.maybe_await(m.before_response())

    def before_response_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.before_response):
                return result.Err(_mismatched_sync)
            m.before_response()
        return result.Ok(None)

    async def before_run_execution(self) -> None:
        for m in self._middleware:
            await transforms.maybe_await(m.before_run_execution())

    def before_run_execution_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.before_run_execution):
                return result.Err(_mismatched_sync)
            m.before_run_execution()
        return result.Ok(None)

    async def transform_input(
        self,
        logger: logging.Logger,
    ) -> execution.CallInput:
        for m in self._middleware:
            t = await transforms.maybe_await(m.transform_input())
            if t.logger is not None:
                logger = t.logger
        return execution.CallInput(logger=logger)

    def transform_input_sync(
        self,
        logger: logging.Logger,
    ) -> result.MaybeError[execution.CallInput]:
        for m in self._middleware:
            if isinstance(m, Middleware):
                return result.Err(_mismatched_sync)

            t = m.transform_input()
            if t.logger is not None:
                logger = t.logger
        return result.Ok(execution.CallInput(logger=logger))
