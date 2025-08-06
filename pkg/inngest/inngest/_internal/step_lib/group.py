import contextvars
import typing

from inngest._internal import server_lib, types

from .base import ResponseInterrupt, SkipInterrupt, StepResponse

# Create a context variable to track if we're in a parallel group.
in_parallel = contextvars.ContextVar("in_parallel", default=False)


class Group:
    async def parallel(
        self,
        callables: tuple[typing.Callable[[], typing.Awaitable[types.T]], ...],
        parallel_mode: server_lib.ParallelMode = server_lib.ParallelMode.WAIT,
    ) -> tuple[types.T, ...]:
        """
        Run multiple steps in parallel.

        Args:
        ----
            callables: An arbitrary number of step callbacks to run. These are callables that contain the step (e.g. `lambda: step.run("my_step", my_step_fn)`.
            parallel_mode: Execution mode. Defaults to `ParallelMode.WAIT`
        """

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
                for r in responses:
                    r.step.set_parallel_mode(parallel_mode)
                raise ResponseInterrupt(responses)

            return outputs
        finally:
            # No longer tell steps that they're running in parallel.
            in_parallel.reset(token)


class GroupSync:
    def parallel(
        self,
        callables: tuple[typing.Callable[[], types.T], ...],
        parallel_mode: server_lib.ParallelMode = server_lib.ParallelMode.WAIT,
    ) -> tuple[types.T, ...]:
        """
        Run multiple steps in parallel in a synchronous context (e.g. not asyncio).

        Args:
        ----
            callables: An arbitrary number of step callbacks to run. These are callables that contain the step (e.g. `lambda: step.run("my_step", my_step_fn)`.
            parallel_mode: Execution mode. Defaults to `ParallelMode.WAIT`
        """

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
                for r in responses:
                    r.step.set_parallel_mode(parallel_mode)
                raise ResponseInterrupt(responses)

            return outputs
        finally:
            # No longer tell steps that they're running in parallel.
            in_parallel.reset(token)
