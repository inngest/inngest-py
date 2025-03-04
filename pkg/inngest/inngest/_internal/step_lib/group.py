import contextvars
import typing

from inngest._internal import types

from .base import ResponseInterrupt, SkipInterrupt, StepResponse

# Create a context variable to track if we're in a parallel group.
in_parallel = contextvars.ContextVar("in_parallel", default=False)

is_fn_async = contextvars.ContextVar("is_fn_async", default=False)


class Group:
    async def parallel(
        self,
        callables: tuple[typing.Callable[[], typing.Awaitable[types.T]], ...],
    ) -> tuple[types.T, ...]:
        """
        Run multiple steps in parallel.

        Args:
        ----
            callables: An arbitrary number of step callbacks to run. These are callables that contain the step (e.g. `lambda: step.run("my_step", my_step_fn)`.
        """

        if is_fn_async.get() is False:
            raise Exception(
                "group.parallel can only be called in an async Inngest function"
            )

        token = in_parallel.set(True)

        try:
            outputs = tuple[types.T]()
            responses: list[StepResponse] = []

            # Discover steps in callables.
            for cb in callables:
                try:
                    output = await cb()
                    outputs = (*outputs, output)
                except ResponseInterrupt as interrupt:
                    responses = [*responses, *interrupt.responses]
                except SkipInterrupt:
                    pass

            if len(responses) > 0:
                raise ResponseInterrupt(responses)

            return outputs
        finally:
            # No longer tell steps that they're running in parallel.
            in_parallel.reset(token)

    def parallel_sync(
        self,
        callables: tuple[typing.Callable[[], types.T], ...],
    ) -> tuple[types.T, ...]:
        """
        Run multiple steps in parallel in a synchronous context (e.g. not asyncio).

        Args:
        ----
            callables: An arbitrary number of step callbacks to run. These are callables that contain the step (e.g. `lambda: step.run("my_step", my_step_fn)`.
        """

        if is_fn_async.get() is True:
            raise Exception(
                "group.parallel_sync can only be called in a non-async Inngest function"
            )

        # Tell steps that they're running in parallel.
        token = in_parallel.set(True)

        try:
            outputs = tuple[types.T]()
            responses: list[StepResponse] = []

            # Discover steps in callables.
            for cb in callables:
                try:
                    output = cb()
                    outputs = (*outputs, output)
                except ResponseInterrupt as interrupt:
                    responses = [*responses, *interrupt.responses]
                except SkipInterrupt:
                    pass

            if len(responses) > 0:
                raise ResponseInterrupt(responses)

            return outputs
        finally:
            # No longer tell steps that they're running in parallel.
            in_parallel.reset(token)
