from __future__ import annotations

import contextlib
import contextvars
import functools
import typing

from inngest._internal import step_lib, types

P = typing.ParamSpec("P")
R = typing.TypeVar("R")

step_context_var = contextvars.ContextVar[step_lib.Step | step_lib.StepSync](
    "step"
)


def is_step_context_set() -> bool:
    try:
        step_context_var.get()
        return True
    except LookupError:
        return False


def get_step_context() -> step_lib.Step | step_lib.StepSync:
    return step_context_var.get()


@contextlib.contextmanager
def set_step_context(step: step_lib.Step | step_lib.StepSync):
    if is_step_context_set():
        raise Exception("Step context already set")

    token = step_context_var.set(step)
    try:
        yield
    finally:
        step_context_var.reset(token)


def step(
    step_id: str,
    *,
    output_type: object = types.EmptySentinel,
) -> typing.Callable[[typing.Callable[P, R]], typing.Callable[P, R]]:
    def decorator(func: typing.Callable[P, R]) -> typing.Callable[P, R]:
        def wrapper(*args: typing.Any, **kwargs: typing.Any) -> R:
            handler = typing.cast(
                typing.Callable[..., typing.Any],
                functools.partial(func, *args, **kwargs),
            )

            if is_step_context_set() is False:
                return handler()

            step = step_context_var.get()
            output = typing.cast(R, step.run(step_id, handler))
            return output

        return wrapper

    return decorator
