"""
Durable sandbox API for sync functions: ctx.step.sandbox and
ctx.group.sandbox.

Every operation is a step with the ID you pass, so a retry or replay reuses
the recorded result instead of calling the API again.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import signal as signal_lib
import time
import typing

from inngest._internal import errors, run_context

from . import durable_common as common
from . import models, ops, validation
from .client import _Info, _ProcessInfo, _SnapshotInfo
from .errors import SandboxError, SandboxErrorCode, SandboxValidationError
from .image import SandboxImage
from .transport import UploadDataSync

if typing.TYPE_CHECKING:
    import types as builtin_types

    from inngest._internal.step_lib import StepSync

_DEFAULT_VCPU: typing.Final = 2
_DEFAULT_MEMORY_MB: typing.Final = 2048
_MAX_NAME_CHARACTERS: typing.Final = 255
_DESTROY_ATTEMPTS: typing.Final = 3


def _run(step: StepSync, step_id: str, call: common.Call) -> common.Result:
    transport = step._client.sandboxes_sync._transport

    def handler() -> common.Result:
        try:
            if call.upload is not None:
                sandbox_id, path, data, mode = call.upload
                value: object = transport.upload(
                    sandbox_id, path, typing.cast(UploadDataSync, data), mode
                )
            else:
                if call.op is None:
                    raise errors.UnreachableError("missing sandbox operation")
                value = transport.run(call.op())
        except (SandboxError, SandboxValidationError) as err:
            return common.handle_error(call, err)
        return common.finish(call, value)

    try:
        raw = step._run(
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


class DurableSandboxToolsSync:
    """
    EXPERIMENTAL: ctx.step.sandbox. Each method runs as a step with the ID you
    pass.
    """

    def __init__(self, step: StepSync) -> None:
        self._step = step
        self.snapshots = _DurableSnapshots(step)

    @typing.overload
    def create(
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
    ) -> DurableSandboxSync: ...

    @typing.overload
    def create(
        self,
        step_id: str,
        *,
        name: str,
        snapshot_id: str,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> DurableSandboxSync: ...

    def create(
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
    ) -> DurableSandboxSync:
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

        return self._create(
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

    def _create(
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
    ) -> DurableSandboxSync:
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
        result = _run(self._step, step_id, common.create_call(body, timeout_ms))
        return _sandbox(self._step, result)

    def list(
        self,
        step_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[DurableSandboxSync]:
        """
        List sandboxes as a step, newest first.
        """

        result = _run(
            self._step,
            step_id,
            common.list_call(validation.list_query(cursor, limit)),
        )
        page, fetched_at = common.parse_page(result)
        return models.SandboxListResult(
            items=[
                DurableSandboxSync(self._step, models.SandboxInfo.from_ref(ref))
                for ref in common.parse_refs(result, "sandboxes")
            ],
            page=page,
            fetched_at=fetched_at,
        )

    def get(self, step_id: str, sandbox_id: str) -> DurableSandboxSync | None:
        """
        Load a sandbox as a step. Returns None if it doesn't exist.
        """

        result = _run(
            self._step,
            step_id,
            common.get_call(validation.validate_uuid(sandbox_id, "sandbox_id")),
        )
        info = common.parse_sandbox(result)
        return None if info is None else DurableSandboxSync(self._step, info)


def _sandbox(step: StepSync, result: common.Result) -> DurableSandboxSync:
    info = common.parse_sandbox(result)
    if info is None:
        raise SandboxValidationError("Sandbox step result has no sandbox")
    return DurableSandboxSync(step, info)


class _DurableSnapshots:
    def __init__(self, step: StepSync) -> None:
        self._step = step

    def list(
        self,
        step_id: str,
        *,
        name: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[DurableSandboxSnapshotSync]:
        """
        List snapshots as a step, newest first. With name, return only
        snapshots with exactly that name.
        """

        query = validation.list_query(cursor, limit)
        if name is not None:
            query["name"] = validation.validate_name(name)
        result = _run(self._step, step_id, common.list_snapshots_call(query))
        page, fetched_at = common.parse_page(result)
        return models.SandboxListResult(
            items=[
                DurableSandboxSnapshotSync(
                    self._step, models.SandboxSnapshotInfo.from_ref(ref)
                )
                for ref in common.parse_refs(result, "snapshots")
            ],
            page=page,
            fetched_at=fetched_at,
        )

    def get(
        self, step_id: str, snapshot_id: str
    ) -> DurableSandboxSnapshotSync | None:
        """
        Load a snapshot as a step. Returns None if it doesn't exist.
        """

        result = _run(
            self._step,
            step_id,
            common.get_snapshot_call(
                validation.validate_uuid(snapshot_id, "snapshot_id")
            ),
        )
        info = common.parse_snapshot(result)
        return (
            None
            if info is None
            else DurableSandboxSnapshotSync(self._step, info)
        )


class DurableSandboxSync(_Info):
    """
    EXPERIMENTAL: A sandbox used from an Inngest function. Each method runs as
    a step with the ID you pass.
    """

    def __init__(self, step: StepSync, info: models.SandboxInfo) -> None:
        self._step = step
        self.info = info
        self.commands = _DurableCommands(self)
        self.processes = _DurableProcesses(self)
        self.files = _DurableFiles(self)

    def wait_until_running(
        self, step_id: str, *, timeout: int | datetime.timedelta
    ) -> DurableSandboxSync:
        """
        Wait as a step for a STARTING sandbox to reach RUNNING. At most 5
        minutes.
        """

        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_RUNNING_TIMEOUT_MS,
        )
        result = _run(
            self._step,
            step_id,
            common.wait_until_running_call(self.info, timeout_ms),
        )
        return _sandbox(self._step, result)

    def pause(
        self, step_id: str, *, timeout: int | datetime.timedelta | None = None
    ) -> DurableSandboxSync:
        """
        Pause the sandbox as a step and wait for PAUSED. Pause keeps its ID,
        memory, filesystem, and remaining runtime.
        """

        return self._change_state(step_id, "pause", timeout)

    def resume(
        self, step_id: str, *, timeout: int | datetime.timedelta | None = None
    ) -> DurableSandboxSync:
        """
        Resume the sandbox as a step and wait for RUNNING.
        """

        return self._change_state(step_id, "resume", timeout)

    def _change_state(
        self,
        step_id: str,
        action: typing.Literal["pause", "resume"],
        timeout: int | datetime.timedelta | None,
    ) -> DurableSandboxSync:
        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
            default_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
        )
        result = _run(
            self._step,
            step_id,
            common.change_state_call(self.info, action, timeout_ms),
        )
        return _sandbox(self._step, result)

    def snapshot(
        self,
        step_id: str,
        *,
        name: str | None = None,
        timeout: int | datetime.timedelta | None = None,
    ) -> DurableSandboxSnapshotSync:
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
                _run(
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
                _run(
                    self._step,
                    f"{step_id}:wait-until-ready",
                    common.wait_snapshot_call(
                        created, timeout_ms, from_snapshot=True
                    ),
                )
            )
        if ready is None:
            raise SandboxValidationError("Snapshot step result has no snapshot")
        return DurableSandboxSnapshotSync(self._step, ready)

    def destroy(self, step_id: str) -> models.SandboxDestroyResult:
        """
        Terminate the sandbox as a step. A sandbox that no longer exists
        counts as TERMINATED, so a repeated destroy succeeds.
        """

        result = _run(self._step, step_id, common.destroy_call(self.info))
        return common.parse_destroy(result)


class _DurableCommands:
    def __init__(self, sandbox: DurableSandboxSync) -> None:
        self._sandbox = sandbox

    def run(
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
        result = _run(
            self._sandbox._step,
            step_id,
            common.exec_call(self._sandbox.info, spec, timeout_ms),
        )
        return common.parse_exec(result)


class _DurableProcesses:
    def __init__(self, sandbox: DurableSandboxSync) -> None:
        self._sandbox = sandbox

    def start(
        self,
        step_id: str,
        command: str | typing.Sequence[str],
        *,
        environment: typing.Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> DurableSandboxProcessSync:
        """
        Start a background process as a step. It keeps running after the step
        ends.
        """

        spec = validation.process_spec(command, environment, cwd)
        step = self._sandbox._step
        result = _run(
            step, step_id, common.start_process_call(self._sandbox.info, spec)
        )
        return _process(step, result)

    def list(
        self,
        step_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[DurableSandboxProcessSync]:
        """
        List the sandbox's background processes as a step.
        """

        step = self._sandbox._step
        result = _run(
            step,
            step_id,
            common.list_processes_call(
                self._sandbox.info, validation.list_query(cursor, limit)
            ),
        )
        page, fetched_at = common.parse_page(result)
        return models.SandboxListResult(
            items=[
                DurableSandboxProcessSync(
                    step, models.SandboxProcessInfo.from_ref(ref)
                )
                for ref in common.parse_refs(result, "processes")
            ],
            page=page,
            fetched_at=fetched_at,
        )

    def get(
        self, step_id: str, process_id: str
    ) -> DurableSandboxProcessSync | None:
        """
        Load a process as a step. Returns None if it doesn't exist.
        """

        step = self._sandbox._step
        result = _run(
            step,
            step_id,
            common.get_process_call(
                self._sandbox.info,
                validation.validate_uuid(process_id, "process_id"),
            ),
        )
        info = common.parse_process(result)
        return None if info is None else DurableSandboxProcessSync(step, info)


class _DurableFiles:
    def __init__(self, sandbox: DurableSandboxSync) -> None:
        self._sandbox = sandbox

    def upload(
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
        result = _run(
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


def _process(
    step: StepSync, result: common.Result
) -> DurableSandboxProcessSync:
    info = common.parse_process(result)
    if info is None:
        raise SandboxValidationError("Process step result has no process")
    return DurableSandboxProcessSync(step, info)


class DurableSandboxProcessSync(_ProcessInfo):
    """
    EXPERIMENTAL: A background process used from an Inngest function.
    """

    def __init__(self, step: StepSync, info: models.SandboxProcessInfo) -> None:
        self._step = step
        self.info = info

    def signal(
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

        _run(
            self._step,
            step_id,
            common.signal_process_call(
                self.info, validation.signal_number(sig), include_children
            ),
        )

    def wait(
        self, step_id: str, *, timeout: int | datetime.timedelta | None = None
    ) -> DurableSandboxProcessSync:
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
        result = _run(
            self._step, step_id, common.wait_process_call(self.info, timeout_ms)
        )
        return _process(self._step, result)

    def get_output(
        self, step_id: str, *, tail_bytes: int | None = None
    ) -> models.SandboxProcessOutput:
        """
        Read retained output as a step. With tail_bytes, return only the end.
        """

        result = _run(
            self._step,
            step_id,
            common.process_output_call(
                self.info, validation.tail_bytes(tail_bytes)
            ),
        )
        return common.parse_output(result)


class DurableSandboxSnapshotSync(_SnapshotInfo):
    """
    EXPERIMENTAL: A snapshot used from an Inngest function.
    """

    def __init__(
        self, step: StepSync, info: models.SandboxSnapshotInfo
    ) -> None:
        self._step = step
        self.info = info

    def wait_until_ready(
        self, step_id: str, *, timeout: int | datetime.timedelta
    ) -> DurableSandboxSnapshotSync:
        """
        Wait as a step for the snapshot to be READY. At most 5 minutes.
        """

        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
        )
        info = common.parse_snapshot(
            _run(
                self._step,
                step_id,
                common.wait_snapshot_call(self.info, timeout_ms),
            )
        )
        if info is None:
            raise SandboxValidationError("Snapshot step result has no snapshot")
        return DurableSandboxSnapshotSync(self._step, info)

    def clone(
        self,
        step_id: str,
        *,
        name: str,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> DurableSandboxSync:
        """
        Create a sandbox from this snapshot as a step.
        """

        return DurableSandboxToolsSync(self._step).create(
            step_id,
            name=name,
            snapshot_id=self.id,
            running_timeout=running_timeout,
            wait=wait,
        )

    def delete(self, step_id: str) -> None:
        """
        Delete the snapshot as a step.
        """

        _run(self._step, step_id, common.delete_snapshot_call(self.info))


def default_name(run_id: str, step_id: str) -> str:
    """
    A name no other run shares. Long step IDs are hashed to fit.
    """

    name = f"{run_id}-{step_id}"
    if len(name) > _MAX_NAME_CHARACTERS:
        digest = hashlib.sha256(step_id.encode("utf-8")).hexdigest()[:32]
        name = f"{run_id}-{digest}"
    return name


class GroupSandboxSync:
    """
    EXPERIMENTAL: A sandbox that lives for a `with` block, grouped in
    the trace. Use ctx.group.sandbox to create one.
    """

    def __init__(
        self,
        step: StepSync,
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
        self._sandbox: DurableSandboxSync | None = None
        self._span: contextlib.AbstractContextManager[None] | None = None

    def __enter__(self) -> DurableSandboxSync:
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
            self._sandbox = DurableSandboxToolsSync(self._step)._create(
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

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: builtin_types.TracebackType | None,
    ) -> None:
        try:
            if self._sandbox is None:
                return
            if exc is None:
                self._destroy_durably(self._sandbox)
            elif isinstance(exc, Exception) and self._is_final(exc):
                self._destroy_now(self._sandbox)
            # Otherwise a step interrupted the block, or a retry is coming.
            # The function resumes later and replays the memoized create, so
            # the sandbox must stay alive.
        finally:
            if self._span is not None:
                self._span.__exit__(exc_type, exc, tb)

    def _is_final(self, err: Exception) -> bool:
        if not errors.is_retriable(err):
            return True
        ctx = self._step._execution._request.ctx
        return (
            ctx.max_attempts is not None and ctx.attempt + 1 >= ctx.max_attempts
        )

    def _destroy_durably(self, sandbox: DurableSandboxSync) -> None:
        try:
            sandbox.destroy(f"{self._id}:destroy")
        except (SandboxError, SandboxValidationError, errors.StepError) as err:
            # A destroy that failed for good must not change the result.
            self._step._client.logger.warning(
                f"Sandbox {sandbox.id} couldn't be destroyed: {err}"
            )

    def _destroy_now(self, sandbox: DurableSandboxSync) -> None:
        """
        Destroy with a plain API call rather than a step. The run is ending,
        and a completed step would reset the run's attempt count, giving the
        failing code another round of retries.
        """

        transport = self._step._client.sandboxes_sync._transport
        for attempt in range(_DESTROY_ATTEMPTS):
            try:
                transport.run(ops.destroy(sandbox.id))
                return
            except SandboxError as err:
                if err.code == SandboxErrorCode.NOT_FOUND.value:
                    return
                if not err.retryable or attempt == _DESTROY_ATTEMPTS - 1:
                    self._step._client.logger.warning(
                        f"Sandbox {sandbox.id} couldn't be destroyed: {err}"
                    )
                    return
            except SandboxValidationError as err:
                self._step._client.logger.warning(
                    f"Sandbox {sandbox.id} couldn't be destroyed: {err}"
                )
                return
            time.sleep(0.5 * (attempt + 1))
