"""
Direct async sandbox client: inngest.Inngest.sandboxes.

Calls run immediately and are not durable. Inside an Inngest function, use
ctx.step.sandbox or ctx.group.sandbox instead.
"""

from __future__ import annotations

import datetime
import signal as signal_lib
import typing

from . import models, ops, validation
from .errors import SandboxError, SandboxValidationError
from .image import SandboxImage
from .transport import SandboxTransport, UploadData

if typing.TYPE_CHECKING:
    import types as builtin_types


class _Info:
    """
    Read-only fields of a sandbox, shared by every sandbox handle.
    """

    info: models.SandboxInfo

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def name(self) -> str:
        return self.info.name

    @property
    def status(self) -> models.SandboxStatus:
        return self.info.status

    @property
    def resources(self) -> models.SandboxResources:
        return self.info.resources

    @property
    def image_ref(self) -> str:
        return self.info.image_ref

    @property
    def image_digest(self) -> str | None:
        return self.info.image_digest

    @property
    def created_at(self) -> datetime.datetime:
        return self.info.created_at

    @property
    def started_at(self) -> datetime.datetime | None:
        return self.info.started_at

    @property
    def ended_at(self) -> datetime.datetime | None:
        return self.info.ended_at

    @property
    def error(self) -> str | None:
        return self.info.error

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r}, name={self.name!r}, status={self.status!r})"


class _ProcessInfo:
    info: models.SandboxProcessInfo

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def sandbox_id(self) -> str:
        return self.info.sandbox_id

    @property
    def command(self) -> tuple[str, ...]:
        return self.info.command

    @property
    def pid(self) -> int | None:
        return self.info.pid

    @property
    def state(self) -> models.SandboxProcessState:
        return self.info.state

    @property
    def exit_code(self) -> int | None:
        return self.info.exit_code

    @property
    def termination_signal(self) -> int | None:
        return self.info.termination_signal

    @property
    def done(self) -> bool:
        return self.info.done

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r}, state={self.state!r})"


class _SnapshotInfo:
    info: models.SandboxSnapshotInfo

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def name(self) -> str | None:
        return self.info.name

    @property
    def status(self) -> models.SandboxSnapshotStatus:
        return self.info.status

    @property
    def resources(self) -> models.SandboxResources:
        return self.info.resources

    @property
    def expires_at(self) -> datetime.datetime:
        return self.info.expires_at

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r}, name={self.name!r}, status={self.status!r})"


def decode_output(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


class Sandboxes:
    """
    EXPERIMENTAL: Direct, non-durable access to sandboxes.

    Use ctx.step.sandbox inside an Inngest function to run each operation as a
    durable step.
    """

    def __init__(self, transport: SandboxTransport) -> None:
        self._transport = transport
        self.snapshots = SandboxSnapshots(transport)

    @typing.overload
    def create(
        self,
        *,
        name: str,
        vcpu: int,
        memory_mb: int,
        environment: typing.Mapping[str, str] | None = None,
        secrets: typing.Sequence[str] | None = None,
        image: str | SandboxImage | None = None,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> CreateSandbox: ...

    @typing.overload
    def create(
        self,
        *,
        name: str,
        snapshot_id: str,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> CreateSandbox: ...

    def create(
        self,
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
    ) -> CreateSandbox:
        """
        Create a sandbox and, unless wait is False, wait for it to reach
        RUNNING.

        Await the result, or use it with `async with` to destroy the sandbox
        when the block exits.

        Creating the same name again with the same configuration returns the
        existing sandbox.

        Args:
        ----
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
        return CreateSandbox(self._transport, body, timeout_ms)

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[Sandbox]:
        """
        List sandboxes, newest first. Includes terminated sandboxes.
        """

        result = await self._transport.run(
            ops.list_sandboxes(validation.list_query(cursor, limit))
        )
        return models.SandboxListResult(
            items=[Sandbox(self._transport, info) for info in result.items],
            page=result.page,
            fetched_at=result.fetched_at,
        )

    async def get(self, sandbox_id: str) -> Sandbox | None:
        """
        Load a sandbox. Returns None if it doesn't exist.
        """

        info = await self._transport.run(
            ops.get_sandbox(validation.validate_uuid(sandbox_id, "sandbox_id"))
        )
        return None if info is None else Sandbox(self._transport, info)


class CreateSandbox:
    """
    A pending create. Await it for the sandbox, or use `async with` to destroy
    the sandbox when the block exits.
    """

    def __init__(
        self,
        transport: SandboxTransport,
        body: dict[str, object],
        running_timeout_ms: int | None,
    ) -> None:
        self._transport = transport
        self._body = body
        self._running_timeout_ms = running_timeout_ms
        self._sandbox: Sandbox | None = None

    async def _create(self) -> Sandbox:
        info = await self._transport.run(
            ops.create(self._body, self._running_timeout_ms)
        )
        return Sandbox(self._transport, info)

    def __await__(self) -> typing.Generator[typing.Any, None, Sandbox]:
        return self._create().__await__()

    async def __aenter__(self) -> Sandbox:
        self._sandbox = await self._create()
        return self._sandbox

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: builtin_types.TracebackType | None,
    ) -> None:
        if self._sandbox is None:
            return
        if exc is None:
            await self._sandbox.destroy()
            return
        try:
            await self._sandbox.destroy()
        except (SandboxError, SandboxValidationError) as err:
            # Raising here would replace the block's own error.
            self._transport._client.logger.warning(
                f"Sandbox {self._sandbox.id} couldn't be destroyed: {err}"
            )


class SandboxSnapshots:
    def __init__(self, transport: SandboxTransport) -> None:
        self._transport = transport

    async def list(
        self,
        *,
        name: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[SandboxSnapshot]:
        """
        List snapshots, newest first. With name, return only snapshots with
        exactly that name.
        """

        query = validation.list_query(cursor, limit)
        if name is not None:
            query["name"] = validation.validate_name(name)
        result = await self._transport.run(ops.list_snapshots(query))
        return models.SandboxListResult(
            items=[
                SandboxSnapshot(self._transport, info) for info in result.items
            ],
            page=result.page,
            fetched_at=result.fetched_at,
        )

    async def get(self, snapshot_id: str) -> SandboxSnapshot | None:
        """
        Load a snapshot. Returns None if it doesn't exist.
        """

        info = await self._transport.run(
            ops.get_snapshot(
                validation.validate_uuid(snapshot_id, "snapshot_id")
            )
        )
        return None if info is None else SandboxSnapshot(self._transport, info)


class Sandbox(_Info):
    """
    EXPERIMENTAL: A sandbox loaded through the direct client. Its fields are
    the state when it was last loaded.
    """

    def __init__(
        self, transport: SandboxTransport, info: models.SandboxInfo
    ) -> None:
        self._transport = transport
        self.info = info
        self.commands = _Commands(self)
        self.processes = _Processes(self)
        self.files = _Files(self)
        self.logs = _Logs(self)

    async def wait_until_running(
        self, *, timeout: int | datetime.timedelta
    ) -> Sandbox:
        """
        Wait for a STARTING sandbox to reach RUNNING. At most 5 minutes.
        """

        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_RUNNING_TIMEOUT_MS,
        )
        info = await self._transport.run(
            ops.wait_until_running(self.info, timeout_ms)
        )
        return Sandbox(self._transport, info)

    async def pause(
        self, *, timeout: int | datetime.timedelta | None = None
    ) -> Sandbox:
        """
        Pause the sandbox and wait for PAUSED. Pause keeps its ID, memory,
        filesystem, and remaining runtime. Waits up to 5 minutes by default.
        """

        return await self._change_state("pause", timeout)

    async def resume(
        self, *, timeout: int | datetime.timedelta | None = None
    ) -> Sandbox:
        """
        Resume a paused sandbox and wait for RUNNING.
        """

        return await self._change_state("resume", timeout)

    async def _change_state(
        self,
        action: typing.Literal["pause", "resume"],
        timeout: int | datetime.timedelta | None,
    ) -> Sandbox:
        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
            default_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
        )
        info = await self._transport.run(
            ops.change_state(self.info, action, timeout_ms)
        )
        return Sandbox(self._transport, info)

    async def snapshot(
        self,
        *,
        name: str | None = None,
        timeout: int | datetime.timedelta | None = None,
    ) -> SandboxSnapshot:
        """
        Snapshot the sandbox's memory and disk while it keeps running, and
        wait for the snapshot to be READY. Waits up to 5 minutes by default.
        """

        if name is not None:
            validation.validate_name(name)
        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
            default_ms=validation.MAX_LIFECYCLE_TIMEOUT_MS,
        )
        created = await self._transport.run(ops.create_snapshot(self.id, name))
        ready = await self._transport.run(
            ops.wait_until_snapshot_ready(created, timeout_ms)
        )
        return SandboxSnapshot(self._transport, ready)

    async def destroy(self) -> models.SandboxDestroyResult:
        """
        Terminate the sandbox. Removes its filesystem, processes, and output.
        """

        return await self._transport.run(ops.destroy(self.id))


class _Commands:
    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    async def run(
        self,
        command: str | typing.Sequence[str],
        *,
        environment: typing.Mapping[str, str] | None = None,
        cwd: str | None = None,
        timeout: int | datetime.timedelta | None = None,
    ) -> models.SandboxCommandResult:
        """
        Run a command and wait for it to exit. A nonzero exit code is a
        result, not an error.

        Args:
        ----
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
        stdout, stderr, exit_code = await self._sandbox._transport.run(
            ops.exec_command(self._sandbox.id, spec, timeout_ms)
        )
        return models.SandboxCommandResult(
            stdout=decode_output(stdout),
            stderr=decode_output(stderr),
            exit_code=exit_code,
        )


class _Processes:
    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    async def start(
        self,
        command: str | typing.Sequence[str],
        *,
        environment: typing.Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> SandboxProcess:
        """
        Start a background process and return once it runs. It keeps running
        after this call returns.
        """

        spec = validation.process_spec(command, environment, cwd)
        info = await self._sandbox._transport.run(
            ops.start_process(self._sandbox.id, spec)
        )
        return SandboxProcess(self._sandbox._transport, info)

    async def list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> models.SandboxListResult[SandboxProcess]:
        """
        List the sandbox's background processes, sorted by ID.
        """

        transport = self._sandbox._transport
        result = await transport.run(
            ops.list_processes(
                self._sandbox.id, validation.list_query(cursor, limit)
            )
        )
        return models.SandboxListResult(
            items=[SandboxProcess(transport, info) for info in result.items],
            page=result.page,
            fetched_at=result.fetched_at,
        )

    async def get(self, process_id: str) -> SandboxProcess | None:
        """
        Load a process. Returns None if it doesn't exist.
        """

        transport = self._sandbox._transport
        info = await transport.run(
            ops.get_process(
                self._sandbox.id,
                validation.validate_uuid(process_id, "process_id"),
            )
        )
        return None if info is None else SandboxProcess(transport, info)


class _Files:
    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    async def upload(
        self,
        path: str,
        data: UploadData,
        *,
        mode: int | None = None,
    ) -> models.SandboxFileUploadResult:
        """
        Write a regular file at an absolute path, replacing any file there.
        The parent directory must exist. At most 100 MiB.

        Args:
        ----
            path: Absolute path in the sandbox.
            data: Bytes, text (written as UTF-8), a binary file object, or an async iterable of bytes.
            mode: File mode, like 0o644. Defaults to 0o644.
        """

        return await self._sandbox._transport.upload(
            self._sandbox.id,
            validation.file_path(path),
            data,
            validation.file_mode(mode),
        )

    async def download(self, path: str) -> bytes:
        """
        Read a regular file at an absolute path. At most 100 MiB.
        """

        return await self._sandbox._transport.download(
            self._sandbox.id, validation.file_path(path)
        )


class _Logs:
    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def stream(
        self, *, follow: bool = False
    ) -> typing.AsyncContextManager[
        typing.AsyncIterator[models.SandboxOutputChunk]
    ]:
        """
        Stream the sandbox's console log.

        ```py
        async with sandbox.logs.stream(follow=True) as chunks:
            async for chunk in chunks:
                print(chunk.data.decode())
        ```
        """

        return self._sandbox._transport.stream(
            "logs.stream",
            f"{ops.sandbox_path(self._sandbox.id)}/logs",
            {"follow": "true" if follow else "false"},
            sandbox_id=self._sandbox.id,
        )


class SandboxProcess(_ProcessInfo):
    """
    EXPERIMENTAL: A background process loaded through the direct client.
    """

    def __init__(
        self,
        transport: SandboxTransport,
        info: models.SandboxProcessInfo,
    ) -> None:
        self._transport = transport
        self.info = info

    async def signal(
        self,
        sig: int | signal_lib.Signals,
        *,
        include_children: bool = True,
    ) -> None:
        """
        Send a Linux signal, like signal.SIGTERM. By default the process's
        descendants get it too, so shell commands don't leave children
        running.
        """

        await self._transport.run(
            ops.signal_process(
                self.info, validation.signal_number(sig), include_children
            )
        )

    async def wait(
        self, *, timeout: int | datetime.timedelta | None = None
    ) -> SandboxProcess:
        """
        Wait for the process to stop. Defaults to 30 seconds; at most 5
        minutes. The timeout ends the wait, not the process.
        """

        timeout_ms = validation.duration_ms(
            timeout,
            field="timeout",
            maximum_ms=validation.MAX_PROCESS_TIMEOUT_MS,
            default_ms=validation.DEFAULT_PROCESS_TIMEOUT_MS,
        )
        info = await self._transport.run(
            ops.wait_process(self.info, timeout_ms)
        )
        return SandboxProcess(self._transport, info)

    async def get_output(
        self, *, tail_bytes: int | None = None
    ) -> models.SandboxProcessOutput:
        """
        Read retained output. About 512 KiB is retained per process. With
        tail_bytes, return only the end.
        """

        return await self._transport.run(
            ops.process_output(self.info, validation.tail_bytes(tail_bytes))
        )

    def stream_output(
        self, *, tail_bytes: int | None = None
    ) -> typing.AsyncContextManager[
        typing.AsyncIterator[models.SandboxOutputChunk]
    ]:
        """
        Stream output as the process writes it. Best effort: a slow reader can
        miss chunks.
        """

        return self._transport.stream(
            "process.stream",
            f"{ops.process_path(self.sandbox_id, self.id)}/output/stream",
            {"tailBytes": str(validation.tail_bytes(tail_bytes))},
            sandbox_id=self.sandbox_id,
            process_id=self.id,
        )


class SandboxSnapshot(_SnapshotInfo):
    """
    EXPERIMENTAL: A snapshot loaded through the direct client.
    """

    def __init__(
        self,
        transport: SandboxTransport,
        info: models.SandboxSnapshotInfo,
    ) -> None:
        self._transport = transport
        self.info = info

    def clone(
        self,
        *,
        name: str,
        running_timeout: int | datetime.timedelta | None = None,
        wait: bool = True,
    ) -> CreateSandbox:
        """
        Create a sandbox from this snapshot. It gets a new ID and the
        snapshot's memory, disk, environment, and resources.
        """

        return Sandboxes(self._transport).create(
            name=name,
            snapshot_id=self.id,
            running_timeout=running_timeout,
            wait=wait,
        )

    async def delete(self) -> None:
        await self._transport.run(ops.delete_snapshot(self.id))
