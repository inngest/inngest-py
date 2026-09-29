from __future__ import annotations

import contextvars
import typing

from inngest._internal import server_lib, types

from .base import ResponseInterrupt, SkipInterrupt, StepResponse

if typing.TYPE_CHECKING:
    from inngest.experimental import experiment

# Create a context variable to track if we're in a parallel group.
in_parallel = contextvars.ContextVar("in_parallel", default=False)


class Group:
    async def experiment(
        self,
        experiment_id: str,
        *,
        variants: typing.Mapping[
            str, typing.Callable[[], typing.Awaitable[types.T]]
        ],
        select: experiment.Selection,
    ) -> experiment.ExperimentResult[types.T]:
        """EXPERIMENTAL: Memoize assignment, then discover the variant's steps."""
        from inngest.experimental import experiment

        return await experiment._run(experiment_id, variants, select)

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
    def experiment(
        self,
        experiment_id: str,
        *,
        variants: typing.Mapping[str, typing.Callable[[], types.T]],
        select: experiment.Selection,
    ) -> experiment.ExperimentResult[types.T]:
        """EXPERIMENTAL: Synchronous experiment orchestration."""
        from inngest.experimental import experiment

        return experiment._run_sync(experiment_id, variants, select)

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
