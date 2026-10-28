"""
Durable sandbox API for async functions: ctx.step.sandbox and
ctx.group.sandbox.

Every operation is a step with the ID you pass, so a retry or replay reuses
the recorded result instead of calling the API again.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import signal as signal_lib
import typing

from inngest._internal import errors, run_context

from . import durable_common as common
from . import models, validation
from .client import _Info, _ProcessInfo, _SnapshotInfo
from .errors import SandboxError, SandboxValidationError
from .image import SandboxImage
from .transport import UploadData

if typing.TYPE_CHECKING:
    import types as builtin_types

    from inngest._internal.step_lib import Step

_DEFAULT_VCPU: typing.Final = 2
_DEFAULT_MEMORY_MB: typing.Final = 2048
_MAX_NAME_CHARACTERS: typing.Final = 255


async def _run(step: Step, step_id: str, call: common.Call) -> common.Result:
    transport = step._client.sandboxes._transport

    async def handler() -> common.Result:
        try:
            if call.upload is not None:
                sandbox_id, path, data, mode = call.upload
                value: object = await transport.upload(
                    sandbox_id, path, typing.cast(UploadData, data), mode
                )
            else:
                if call.op is None:
                    raise errors.UnreachableError("missing sandbox operation")
                value = await transport.run(call.op())
        except (SandboxError, SandboxValidationError) as err:
            return common.handle_error(call, err)
        return common.finish(call, value)

    try:
        raw = await step._run(
            step_id,
            handler,
            display_name=call.display_name,
            origin=call.origin,
        )
    except errors.StepError as err:
        rebuilt = common.rebuild_error(err)
        if rebuilt is None:
            raise
        raise rebuilt from err
    return common.check_result(raw, call.action)


class DurableSandboxTools:
    """
    EXPERIMENTAL: ctx.step.sandbox. Each method runs as a step with the ID you
    pass.
    """

    def __init__(self, step: Step) -> None:
        self._step = step
        self.snapshots = _DurableSnapshots(step)

    @typing.overload
    async def create(
        self,
        step_id: str,
        *,
        name: str,
        vcpu: int,
        memory_mb: int,
        environment: typing.Mapping[str, str] | None = None,
        secrets: typing.Sequence[str] | None = None,
        image: str | SandboxImage | None = None,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> DurableSandbox: ...

    @typing.overload
    async def create(
        self,
        step_id: str,
        *,
        name: str,
        snapshot_id: str,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> DurableSandbox: ...

    async def create(
        self,
        step_id: str,
        *,
        name: str,
        vcpu: int | None = None,
        memory_mb: int | None = None,
        environment: typing.Mapping[str, str] | None = None,
        secrets: typing.Sequence[str] | None = None,
        image: str | SandboxImage | None = None,
        snapshot_id: str | None = None,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> DurableSandbox:
        """
        Create a sandbox as a step and, unless wait is False, wait for it to
        reach RUNNING. Destroy it when you're done, or use ctx.group.sandbox
        to destroy it for you.

        Give it a stable, job-specific name: a retried create with the same
        name and configuration returns the same sandbox.

        Args:
        ----
            step_id: Durable step ID.
            name: Stable identity for an active sandbox. Up to 255 characters.
            vcpu: vCPUs for a fresh sandbox.
            memory_mb: Memory for a fresh sandbox.
            environment: Environment inherited by commands and processes.
            secrets: Workspace secret names, each injected under the same environment variable name.
            image: Published image to start from: image.inngest("base") (the default), image.custom(ref), or a reference like "my-image:v1". Resolved once when the sandbox is created.
            snapshot_id: Start from this snapshot instead. Takes the snapshot's resources and environment.
            running_timeout: How long to wait for RUNNING. Defaults to 120 seconds; at most 5 minutes. int is milliseconds.
            wait: Set to False to return as soon as Create is accepted.
        """

        return await self._create(
            step_id,
            name=name,
            vcpu=vcpu,
            memory_mb=memory_mb,
            environment=environment,
            secrets=secrets,
            image=image,
            snapshot_id=snapshot_id,
            running_timeout=running_timeout,
            wait=wait,
        )

    async def _create(
        self,
        step_id: str,
        *,
        name: str,
        vcpu: int | None,
        memory_mb: int | None,
        environment: typing.Mapping[str, str] | None,
        secrets: typing.Sequence[str] | None,
        image: str | SandboxImage | None,
        snapshot_id: str | None,
        running_timeout: int | datetime.timedelta | None,
        wait: bool = True,
    ) -> DurableSandbox:
        body = validation.create_body(
            name=name,
            vcpu=vcpu,
            memory_mb=memory_mb,
            environment=environment,
            secrets=secrets,
            image=image,
            snapshot_id=snapshot_id,
        )
        timeout_ms = (
            validation.duration_ms(
                running_timeout,
                field="running_timeout",
                maximum_ms=validation.MAX_RUNNING_TIMEOUT_MS,
                default_ms=validation.DEFAULT_RUNNING_TIMEOUT_MS,
            )
            if wait
            else None
        )
        result = await _run(
            self._step, step_id, common.create_call(body, timeout_ms)
        )
        return _sandbox(self._step, result)

    async def list(
        self,
        step_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[DurableSandbox]:
        """
        List sandboxes as a step, newest first.
        """

        result = await _run(
            self._step,
            step_id,
            common.list_call(validation.list_query(cursor, limit)),
        )
        page, fetched_at = common.parse_page(result)
        return models.SandboxListResult(
            items=[
                DurableSandbox(self._step, models.SandboxInfo.from_ref(ref))
                for ref in common.parse_refs(result, "sandboxes")
            ],
            page=page,
            fetched_at=fetched_at,
        )

    async def get(self, step_id: str, sandbox_id: str) -> DurableSandbox | None:
        """
        Load a sandbox as a step. Returns None if it doesn't exist.
        """

        result = await _run(
            self._step,
            step_id,
            common.get_call(validation.validate_uuid(sandbox_id, "sandbox_id")),
        )
        info = common.parse_sandbox(result)
        return None if info is None else DurableSandbox(self._step, info)


def _sandbox(step: Step, result: common.Result) -> DurableSandbox:
    info = common.parse_sandbox(result)
    if info is None:
        raise SandboxValidationError("Sandbox step result has no sandbox")
    return DurableSandbox(step, info)


class _DurableSnapshots:
    def __init__(self, step: Step) -> None:
        self._step = step

    async def list(
        self,
        step_id: str,
        *,
        name: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[DurableSandboxSnapshot]:
        """
        List snapshots as a step, newest first. With name, return only
        snapshots with exactly that name.
        """

        query = validation.list_query(cursor, limit)
        if name is not None:
            query["name"] = validation.validate_name(name)
        result = await _run(
            self._step, step_id, common.list_snapshots_call(query)
        )
        page, fetched_at = common.parse_page(result)
        return models.SandboxListResult(
            items=[
                DurableSandboxSnapshot(
                    self._step, models.SandboxSnapshotInfo.from_ref(ref)
                )
                for ref in common.parse_refs(result, "snapshots")
            ],
            page=page,
            fetched_at=fetched_at,
        )

    async def get(
        self, step_id: str, snapshot_id: str
    ) -> DurableSandboxSnapshot | None:
        """
        Load a snapshot as a step. Returns None if it doesn't exist.
        """

        result = await _run(
            self._step,
            step_id,
            common.get_snapshot_call(
                validation.validate_uuid(snapshot_id, "snapshot_id")
            ),
        )
        info = common.parse_snapshot(result)
        return (
            None if info is None else DurableSandboxSnapshot(self._step, info)
        )


class DurableSandbox(_Info):
    """
    EXPERIMENTAL: A sandbox used from an Inngest function. Each method runs as
    a step with the ID you pass.
    """

    def __init__(self, step: Step, info: models.SandboxInfo) -> None:
        self._step = step
        self.info = info
        self.commands = _DurableCommands(self)
        self.processes = _DurableProcesses(self)
        self.files = _DurableFiles(self)

    async def wait_until_running(
        self, step_id: str, *, timeout: int | datetime.timedelta
    ) -> DurableSandbox:
        """
        Wait as a step for a STARTING sandbox to reach RUNNING. At most 5
        minutes.
        """

        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_RUNNING_TIMEOUT_MS,
        )
        result = await _run(
            self._step,
            step_id,
            common.wait_until_running_call(self.info, timeout_ms),
        )
        return _sandbox(self._step, result)

    async def pause(
        self, step_id: str, *, timeout: int | datetime.timedelta | None = None
    ) -> DurableSandbox:
        """
        Pause the sandbox as a step and wait for PAUSED. Pause keeps its ID,
        memory, filesystem, and remaining runtime.
        """

        return await self._change_state(step_id, "pause", timeout)

    async def resume(
        self, step_id: str, *, timeout: int | datetime.timedelta | None = None
    ) -> DurableSandbox:
        """
        Resume the sandbox as a step and wait for RUNNING.
        """

        return await self._change_state(step_id, "resume", timeout)

    async def _change_state(
        self,
        step_id: str,
        action: typing.Literal["pause", "resume"],
        timeout: int | datetime.timedelta | None,
    ) -> DurableSandbox:
        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
            default_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
        )
        result = await _run(
            self._step,
            step_id,
            common.change_state_call(self.info, action, timeout_ms),
        )
        return _sandbox(self._step, result)

    async def snapshot(
        self,
        step_id: str,
        *,
        name: str | None = None,
        timeout: int | datetime.timedelta | None = None,
    ) -> DurableSandboxSnapshot:
        """
        Snapshot the sandbox and wait for the snapshot to be READY. Runs two
        steps: step_id creates the snapshot, and step_id + ":wait-until-ready"
        waits for it, so a retry of the wait doesn't create a second snapshot.
        """

        if name is not None:
            validation.validate_name(name)
        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
            default_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
        )
        with run_context.use_span(
            run_context.Span(id=step_id, name=step_id, kind="snapshot")
        ):
            created = common.parse_snapshot(
                await _run(
                    self._step,
                    step_id,
                    common.create_snapshot_call(self.info, name),
                )
            )
            if created is None:
                raise SandboxValidationError(
                    "Snapshot step result has no snapshot"
                )
            ready = common.parse_snapshot(
                await _run(
                    self._step,
                    f"{step_id}:wait-until-ready",
                    common.wait_snapshot_call(
                        created, timeout_ms, from_snapshot=True
                    ),
                )
            )
        if ready is None:
            raise SandboxValidationError("Snapshot step result has no snapshot")
        return DurableSandboxSnapshot(self._step, ready)

    async def destroy(self, step_id: str) -> models.SandboxDestroyResult:
        """
        Terminate the sandbox as a step. A sandbox that no longer exists
        counts as TERMINATED, so a repeated destroy succeeds.
        """

        result = await _run(self._step, step_id, common.destroy_call(self.info))
        return common.parse_destroy(result)


class _DurableCommands:
    def __init__(self, sandbox: DurableSandbox) -> None:
        self._sandbox = sandbox

    async def run(
        self,
        step_id: str,
        command: str | typing.Sequence[str],
        *,
        environment: typing.Mapping[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | datetime.timedelta | None = None,
    ) -> models.SandboxCommandResult:
        """
        Run a command as a step and wait for it to exit. A nonzero exit code
        is a result, not an error.

        The step keeps at most 2 MiB of output, from the end of each stream.

        Args:
        ----
            step_id: Durable step ID.
            command: A string runs through /bin/sh -c, so pipes and variables work. A list runs as argv without a shell.
            environment: Overrides matching sandbox environment values for this command.
            cwd: Working directory. Defaults to /.
            timeout: Defaults to 30 seconds; at most 5 minutes. int is milliseconds. Use a process for longer work.
        """

        spec = validation.process_spec(command, environment, cwd)
        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_PROCESS_TIMEOUT_MS,
            default_ms=validation.DEFAULT_PROCESS_TIMEOUT_MS,
        )
        result = await _run(
            self._sandbox._step,
            step_id,
            common.exec_call(self._sandbox.info, spec, timeout_ms),
        )
        return common.parse_exec(result)


class _DurableProcesses:
    def __init__(self, sandbox: DurableSandbox) -> None:
        self._sandbox = sandbox

    async def start(
        self,
        step_id: str,
        command: str | typing.Sequence[str],
        *,
        environment: typing.Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> DurableSandboxProcess:
        """
        Start a background process as a step. It keeps running after the step
        ends.
        """

        spec = validation.process_spec(command, environment, cwd)
        step = self._sandbox._step
        result = await _run(
            step, step_id, common.start_process_call(self._sandbox.info, spec)
        )
        return _process(step, result)

    async def list(
        self,
        step_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[DurableSandboxProcess]:
        """
        List the sandbox's background processes as a step.
        """

        step = self._sandbox._step
        result = await _run(
            step,
            step_id,
            common.list_processes_call(
                self._sandbox.info, validation.list_query(cursor, limit)
            ),
        )
        page, fetched_at = common.parse_page(result)
        return models.SandboxListResult(
            items=[
                DurableSandboxProcess(
                    step, models.SandboxProcessInfo.from_ref(ref)
                )
                for ref in common.parse_refs(result, "processes")
            ],
            page=page,
            fetched_at=fetched_at,
        )

    async def get(
        self, step_id: str, process_id: str
    ) -> DurableSandboxProcess | None:
        """
        Load a process as a step. Returns None if it doesn't exist.
        """

        step = self._sandbox._step
        result = await _run(
            step,
            step_id,
            common.get_process_call(
                self._sandbox.info,
                validation.validate_uuid(process_id, "process_id"),
            ),
        )
        info = common.parse_process(result)
        return None if info is None else DurableSandboxProcess(step, info)


class _DurableFiles:
    def __init__(self, sandbox: DurableSandbox) -> None:
        self._sandbox = sandbox

    async def upload(
        self,
        step_id: str,
        path: str,
        data: bytes | str,
        *,
        mode: int | None = None,
    ) -> models.SandboxFileUploadResult:
        """
        Write a regular file as a step, replacing any file there. The parent
        directory must exist. Only the path and byte count are recorded, not
        the data.

        Args:
        ----
            step_id: Durable step ID.
            path: Absolute path in the sandbox.
            data: Bytes, or text written as UTF-8. At most 100 MiB.
            mode: File mode, like 0o644. Defaults to 0o644.
        """

        if not isinstance(data, (bytes, str)):
            raise SandboxValidationError("data must be bytes or str")
        result = await _run(
            self._sandbox._step,
            step_id,
            common.upload_call(
                self._sandbox.info,
                validation.file_path(path),
                data,
                validation.file_mode(mode),
            ),
        )
        return common.parse_upload(result)


def _process(step: Step, result: common.Result) -> DurableSandboxProcess:
    info = common.parse_process(result)
    if info is None:
        raise SandboxValidationError("Process step result has no process")
    return DurableSandboxProcess(step, info)


class DurableSandboxProcess(_ProcessInfo):
    """
    EXPERIMENTAL: A background process used from an Inngest function.
    """

    def __init__(self, step: Step, info: models.SandboxProcessInfo) -> None:
        self._step = step
        self.info = info

    async def signal(
        self,
        step_id: str,
        sig: int | signal_lib.Signals,
        *,
        include_children: bool = True,
    ) -> None:
        """
        Send a Linux signal as a step, like signal.SIGTERM. By default the
        process's descendants get it too.
        """

        await _run(
            self._step,
            step_id,
            common.signal_process_call(
                self.info, validation.signal_number(sig), include_children
            ),
        )

    async def wait(
        self, step_id: str, *, timeout: int | datetime.timedelta | None = None
    ) -> DurableSandboxProcess:
        """
        Wait as a step for the process to stop. Defaults to 30 seconds; at
        most 5 minutes. The timeout ends the wait, not the process.
        """

        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_PROCESS_TIMEOUT_MS,
            default_ms=validation.DEFAULT_PROCESS_TIMEOUT_MS,
        )
        result = await _run(
            self._step, step_id, common.wait_process_call(self.info, timeout_ms)
        )
        return _process(self._step, result)

    async def get_output(
        self, step_id: str, *, tail_bytes: int | None = None
    ) -> models.SandboxProcessOutput:
        """
        Read retained output as a step. With tail_bytes, return only the end.
        """

        result = await _run(
            self._step,
            step_id,
            common.process_output_call(
                self.info, validation.tail_bytes(tail_bytes)
            ),
        )
        return common.parse_output(result)


class DurableSandboxSnapshot(_SnapshotInfo):
    """
    EXPERIMENTAL: A snapshot used from an Inngest function.
    """

    def __init__(self, step: Step, info: models.SandboxSnapshotInfo) -> None:
        self._step = step
        self.info = info

    async def wait_until_ready(
        self, step_id: str, *, timeout: int | datetime.timedelta
    ) -> DurableSandboxSnapshot:
        """
        Wait as a step for the snapshot to be READY. At most 5 minutes.
        """

        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
        )
        info = common.parse_snapshot(
            await _run(
                self._step,
                step_id,
                common.wait_snapshot_call(self.info, timeout_ms),
            )
        )
        if info is None:
            raise SandboxValidationError("Snapshot step result has no snapshot")
        return DurableSandboxSnapshot(self._step, info)

    async def clone(
        self,
        step_id: str,
        *,
        name: str,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> DurableSandbox:
        """
        Create a sandbox from this snapshot as a step.
        """

        return await DurableSandboxTools(self._step).create(
            step_id,
            name=name,
            snapshot_id=self.id,
            running_timeout=running_timeout,
            wait=wait,
        )

    async def delete(self, step_id: str) -> None:
        """
        Delete the snapshot as a step.
        """

        await _run(self._step, step_id, common.delete_snapshot_call(self.info))


def default_name(run_id: str, step_id: str) -> str:
    """
    A name no other run shares. Long step IDs are hashed to fit.
    """

    name = f"{run_id}-{step_id}"
    if len(name) > _MAX_NAME_CHARACTERS:
        digest = hashlib.sha256(step_id.encode("utf-8")).hexdigest()[:32]
        name = f"{run_id}-{digest}"
    return name


class GroupSandbox:
    """
    EXPERIMENTAL: A sandbox that lives for an `async with` block, grouped in
    the trace. Use ctx.group.sandbox to create one.
    """

    def __init__(
        self,
        step: Step,
        group_id: str,
        *,
        name: str | None,
        vcpu: int | None,
        memory_mb: int | None,
        environment: typing.Mapping[str, str] | None,
        secrets: typing.Sequence[str] | None,
        image: str | SandboxImage | None,
        snapshot_id: str | None,
        running_timeout: int | datetime.timedelta | None,
    ) -> None:
        self._step = step
        self._id = group_id
        self._name = name
        self._vcpu = vcpu
        self._memory_mb = memory_mb
        self._environment = environment
        self._secrets = secrets
        self._image = image
        self._snapshot_id = snapshot_id
        self._running_timeout = running_timeout
        self._sandbox: DurableSandbox | None = None
        self._span: contextlib.AbstractContextManager[None] | None = None

    async def __aenter__(self) -> DurableSandbox:
        # The ID the create step will get, so a reused group ID still gets
        # its own name and trace group.
        step_id = self._step._step_id_counter.peek(self._id)
        name = self._name
        if name is None:
            run = run_context.current_run.get()
            run_id = run.ctx.run_id if run is not None else ""
            name = default_name(run_id, step_id)

        vcpu, memory_mb = self._vcpu, self._memory_mb
        if self._snapshot_id is None:
            vcpu = _DEFAULT_VCPU if vcpu is None else vcpu
            memory_mb = _DEFAULT_MEMORY_MB if memory_mb is None else memory_mb

        span = run_context.use_span(
            run_context.Span(
                id=step_id, name=f"Sandbox {self._id}", kind="sandbox"
            )
        )
        span.__enter__()
        self._span = span
        try:
            self._sandbox = await DurableSandboxTools(self._step)._create(
                self._id,
                name=name,
                vcpu=vcpu,
                memory_mb=memory_mb,
                environment=self._environment,
                secrets=self._secrets,
                image=self._image,
                snapshot_id=self._snapshot_id,
                running_timeout=self._running_timeout,
            )
        except BaseException as err:
            span.__exit__(type(err), err, err.__traceback__)
            raise
        return self._sandbox

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: builtin_types.TracebackType | None,
    ) -> None:
        try:
            if self._sandbox is None:
                return
            # Anything else is a step interrupting the block. The function
            # resumes later and replays the memoized create, so the sandbox
            # must stay alive.
            if exc is None or isinstance(exc, Exception):
                await self._destroy(self._sandbox)
        finally:
            if self._span is not None:
                self._span.__exit__(exc_type, exc, tb)

    async def _destroy(self, sandbox: DurableSandbox) -> None:
        """
        Destroy the sandbox in a step whenever the block ends, even on an
        error. A retry couldn't use the destroyed sandbox, so the function's
        errors are final from here on.
        """

        try:
            await sandbox.destroy(f"{self._id}:destroy")
        except (SandboxError, SandboxValidationError, errors.StepError) as err:
            # A destroy that failed for good must not change the result.
            self._step._client.logger.warning(
                f"Sandbox {sandbox.id} couldn't be destroyed: {err}"
            )
        self._step._execution.fail_finally()
