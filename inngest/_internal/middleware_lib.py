import inspect
import typing

from . import errors, result

BlankHook = typing.Callable[[], typing.Awaitable[None] | None]


class Middleware:
    async def after_run_execution(self) -> None:
        """
        Called after a function run is done executing. Called once per run
        regardless of the number of steps. Will still be called if the run
        failed.
        """

        return None

    async def before_response(self) -> None:
        """
        Called after the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """

        return None

    async def before_run_execution(self) -> None:
        """
        Called when a function run starts executing. Called once per run
        regardless of the number of steps.
        """

        return None


class MiddlewareSync:
    def after_run_execution(self) -> None:
        """
        Called after a function run is done executing. Called once per run
        regardless of the number of steps. Will still be called if the run
        failed.
        """

        return None

    def before_response(self) -> None:
        """
        Called after the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """

        return None

    def before_run_execution(self) -> None:
        """
        Called when a function run starts executing. Called once per run
        regardless of the number of steps.
        """

        return None


class MiddlewareManager:
    def __init__(
        self,
        middleware: list[Middleware | MiddlewareSync],
    ):
        self._middleware = middleware

    def after_run_execution_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.after_run_execution):
                return result.Err(
                    errors.MismatchedSync(
                        "encountered async middleware in non-async context"
                    )
                )
            m.after_run_execution()
        return result.Ok(None)

    def before_response_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.before_response):
                return result.Err(
                    errors.MismatchedSync(
                        "encountered async middleware in non-async context"
                    )
                )
            m.before_response()
        return result.Ok(None)

    def before_run_execution_sync(self) -> result.MaybeError[None]:
        for m in self._middleware:
            if inspect.iscoroutinefunction(m.before_run_execution):
                return result.Err(
                    errors.MismatchedSync(
                        "encountered async middleware in non-async context"
                    )
                )
            m.before_run_execution()
        return result.Ok(None)
