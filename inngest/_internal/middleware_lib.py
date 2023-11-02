import dataclasses
import inspect
import typing

from . import errors, result

BlankHook = typing.Callable[[], typing.Awaitable[None] | None]


def noop() -> None:
    pass


@dataclasses.dataclass
class Middleware:
    after_execution: BlankHook | None = None
    before_execution: BlankHook | None = None


class MiddlewareManager:
    def __init__(
        self,
        middleware: list[Middleware],
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
