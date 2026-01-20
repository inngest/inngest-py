from __future__ import annotations

import contextlib
import contextvars
import functools
import typing

from inngest._internal import step_lib

_TParams = typing.ParamSpec("_TParams")
_TReturn = typing.TypeVar("_TReturn")

_step_context_var = contextvars.ContextVar[step_lib.Step | step_lib.StepSync](
    "step"
)


def _is_step_context_set() -> bool:
    try:
        _step_context_var.get()
        return True
    except LookupError:
        return False


def get_step_context() -> step_lib.Step | step_lib.StepSync:
    return _step_context_var.get()


@contextlib.contextmanager
def set_step_context(
    step: step_lib.Step | step_lib.StepSync,
) -> typing.Generator[None, None, None]:
    if _is_step_context_set():
        raise Exception("Step context already set")

    token = _step_context_var.set(step)
    try:
        yield
    finally:
        _step_context_var.reset(token)


def step(
    step_id: str,
) -> typing.Callable[
    [typing.Callable[_TParams, _TReturn]], typing.Callable[_TParams, _TReturn]
]:
    """
    A decorator that turns a normal function into a step function. When the
    decorated function is called within an Inngest function, it will be wrapped
    with a `step.run`. When the decorated function is called outside of an
    Inngest function, it will be called directly (i.e. not wrapped with
    `step.run`)
    """

    def decorator(
        func: typing.Callable[_TParams, _TReturn],
    ) -> typing.Callable[_TParams, _TReturn]:
        @functools.wraps(func)
        def wrapper(
            *args: _TParams.args, **kwargs: _TParams.kwargs
        ) -> _TReturn:
            handler = functools.partial(func, *args, **kwargs)

            if _is_step_context_set() is False:
                return handler()

            step = _step_context_var.get()
            output = typing.cast(_TReturn, step.run(step_id, handler))  # type: ignore[arg-type]
            return output

        return wrapper

    return decorator
