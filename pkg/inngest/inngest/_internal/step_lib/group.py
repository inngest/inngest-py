from __future__ import annotations

import contextvars
import datetime
import typing

from inngest._internal import sandbox_lib, server_lib, types

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

    def sandbox(
        self,
        group_id: str,
        *,
        name: str | None = None,
        vcpu: int | None = None,
        memory_mb: int | None = None,
        environment: typing.Mapping[str, str] | None = None,
        secrets: typing.Sequence[str] | None = None,
        image: str | sandbox_lib.SandboxImage | None = None,
        snapshot_id: str | None = None,
        running_timeout: int | datetime.timedelta | None = None,
    ) -> sandbox_lib.GroupSandbox:
        """
        EXPERIMENTAL: A sandbox that lives for an `async with` block, grouped in
        the trace.

        ```py
        async with ctx.group.sandbox("build") as sandbox:
            result = await sandbox.commands.run("test", "pytest -q")
        ```

        Step group_id creates the sandbox and step group_id + ":destroy"
        destroys it when the block ends, even when the block raises. A retry
        couldn't use the destroyed sandbox, so the function's errors are final
        after that.

        Args:
        ----
            group_id: Durable ID for the group and its create step.
            name: Defaults to a name no other run shares.
            vcpu: Defaults to 2.
            memory_mb: Defaults to 2048.
            environment: Environment inherited by commands and processes.
            secrets: Workspace secret names, each injected under the same environment variable name.
            image: Published image to start from: image.inngest("base") (the default), image.custom(ref), or a reference like "my-image:v1". Resolved once when the sandbox is created.
            snapshot_id: Start from this snapshot instead.
            running_timeout: How long to wait for RUNNING. Defaults to 120 seconds.
        """

        from inngest._internal import run_context
        from inngest._internal.step_lib.step_async import Step

        run = run_context.current_run.get()
        step = None if run is None else run.ctx.step
        if not isinstance(step, Step):
            raise RuntimeError(
                "group.sandbox() must be called inside an Inngest function"
            )
        return sandbox_lib.GroupSandbox(
            step,
            group_id,
            name=name,
            vcpu=vcpu,
            memory_mb=memory_mb,
            environment=environment,
            secrets=secrets,
            image=image,
            snapshot_id=snapshot_id,
            running_timeout=running_timeout,
        )

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

    def sandbox(
        self,
        group_id: str,
        *,
        name: str | None = None,
        vcpu: int | None = None,
        memory_mb: int | None = None,
        environment: typing.Mapping[str, str] | None = None,
        secrets: typing.Sequence[str] | None = None,
        image: str | sandbox_lib.SandboxImage | None = None,
        snapshot_id: str | None = None,
        running_timeout: int | datetime.timedelta | None = None,
    ) -> sandbox_lib.GroupSandboxSync:
        """
        EXPERIMENTAL: A sandbox that lives for a `with` block, grouped in
        the trace.

        ```py
        with ctx.group.sandbox("build") as sandbox:
            result = sandbox.commands.run("test", "pytest -q")
        ```

        Step group_id creates the sandbox and step group_id + ":destroy"
        destroys it when the block ends, even when the block raises. A retry
        couldn't use the destroyed sandbox, so the function's errors are final
        after that.

        Args:
        ----
            group_id: Durable ID for the group and its create step.
            name: Defaults to a name no other run shares.
            vcpu: Defaults to 2.
            memory_mb: Defaults to 2048.
            environment: Environment inherited by commands and processes.
            secrets: Workspace secret names, each injected under the same environment variable name.
            image: Published image to start from: image.inngest("base") (the default), image.custom(ref), or a reference like "my-image:v1". Resolved once when the sandbox is created.
            snapshot_id: Start from this snapshot instead.
            running_timeout: How long to wait for RUNNING. Defaults to 120 seconds.
        """

        from inngest._internal import run_context
        from inngest._internal.step_lib.step_sync import StepSync

        run = run_context.current_run.get()
        step = None if run is None else run.ctx.step
        if not isinstance(step, StepSync):
            raise RuntimeError(
                "group.sandbox() must be called inside an Inngest function"
            )
        return sandbox_lib.GroupSandboxSync(
            step,
            group_id,
            name=name,
            vcpu=vcpu,
            memory_mb=memory_mb,
            environment=environment,
            secrets=secrets,
            image=image,
            snapshot_id=snapshot_id,
            running_timeout=running_timeout,
        )

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
