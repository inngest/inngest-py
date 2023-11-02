import inspect
import typing

from . import errors, result

BlankHook = typing.Callable[[], typing.Awaitable[None] | None]


class Middleware:
    async def after_execution(self) -> None:
        """
        Called after a function run is done executing. Called once per run
        regardless of the number of steps. Will still be called if the run
        failed.
        """

        return None

    async def before_execution(self) -> None:
        """
        Called when a function run starts executing. Called once per run
        regardless of the number of steps.
        """

        return None


class MiddlewareSync:
    def after_execution(self) -> None:
        """
        Called after a function run is done executing. Called once per run
        regardless of the number of steps. Will still be called if the run
        failed.
        """

        return None

    def before_execution(self) -> None:
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

    def after_execution_sync(self) -> result.OkOrError[None]:
        for m in self._middleware:
            if m.after_execution:
                if inspect.iscoroutinefunction(m.after_execution):
                    return result.Err(
                        errors.MismatchedSync(
                            "encountered async middleware in non-async context"
                        )
                    )
                m.after_execution()
        return result.Ok(None)

    def before_execution_sync(self) -> result.OkOrError[None]:
        for m in self._middleware:
            if m.before_execution:
                if inspect.iscoroutinefunction(m.before_execution):
                    return result.Err(
                        errors.MismatchedSync(
                            "encountered async middleware in non-async context"
                        )
                    )
                m.before_execution()
        return result.Ok(None)
