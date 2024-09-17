import contextvars
import typing

from inngest._internal import types

from .base import ResponseInterrupt, SkipInterrupt, StepResponse

# Create a context variable to track if we're in a parallel group
in_parallel = contextvars.ContextVar("in_parallel", default=False)


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

        token = in_parallel.set(True)
        try:
            outputs = tuple[types.T]()
            responses: list[StepResponse] = []
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
            in_parallel.reset(token)

    def parallel_sync(
        self,
        callables: tuple[typing.Callable[[], types.T], ...],
    ) -> tuple[types.T, ...]:
        """
        Run multiple steps in parallel.

        Args:
        ----
            callables: An arbitrary number of step callbacks to run. These are callables that contain the step (e.g. `lambda: step.run("my_step", my_step_fn)`.
        """

        token = in_parallel.set(True)
        try:
            outputs = tuple[types.T]()
            responses: list[StepResponse] = []
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
            in_parallel.reset(token)
