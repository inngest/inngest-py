"""
Sandbox REST operations, written once without I/O.

Each operation is a generator that yields a Request or a Sleep and receives
the Response. The async and sync transports drive the same generators, so
polling and validation behave identically in both. A transport throws a
SandboxError into the generator when a request fails, so an operation can keep
polling through retryable errors.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import time
import typing
import urllib.parse

from . import models
from .errors import (
    SandboxAction,
    SandboxError,
    SandboxErrorCode,
    SandboxValidationError,
)

# How often polling operations check for a state change.
POLL_INTERVAL_SECONDS: typing.Final = 1.0

# Extra time an HTTP request may take beyond the operation's own timeout.
_REQUEST_SLACK_SECONDS: typing.Final = 30.0


@dataclasses.dataclass
class Request:
    action: SandboxAction
    method: str
    path: str
    statuses: tuple[int, ...]
    query: dict[str, str] | None = None

    # JSON body. None sends no body.
    body: object = None

    sandbox_id: str | None = None
    process_id: str | None = None
    snapshot_id: str | None = None

    # Read timeout in seconds. None uses the transport default.
    timeout: float | None = None


@dataclasses.dataclass
class Response:
    status: int
    data: object = None
    metadata: object = None
    page: object = None


@dataclasses.dataclass
class Sleep:
    seconds: float


T = typing.TypeVar("T")

# An operation: yields requests and sleeps, receives responses, returns T.
Op: typing.TypeAlias = typing.Generator[Request | Sleep, Response | None, T]


def _send(
    request: Request,
) -> typing.Generator[Request, Response | None, Response]:
    response = yield request
    if response is None:
        raise SandboxValidationError("sandbox transport returned no response")
    return response


def sandbox_path(sandbox_id: str) -> str:
    return f"/v2/sandboxes/{urllib.parse.quote(sandbox_id, safe='')}"


def process_path(sandbox_id: str, process_id: str) -> str:
    return f"{sandbox_path(sandbox_id)}/processes/{urllib.parse.quote(process_id, safe='')}"


def snapshot_path(snapshot_id: str) -> str:
    return f"/v2/snapshots/{urllib.parse.quote(snapshot_id, safe='')}"


def _ms(ms: int) -> str:
    return f"{ms}ms"


def _list_items(data: object, context: str) -> list[object]:
    # The API omits data when a list is empty.
    if data is None:
        return []
    if not isinstance(data, list):
        raise SandboxValidationError(f"Invalid {context}: expected a list")
    return data


def _fetched_at(metadata: object) -> str:
    if isinstance(metadata, dict):
        value = metadata.get("fetchedAt")
        if isinstance(value, str):
            return value
    return ""


def decode_base64(value: object, context: str) -> bytes:
    if value is None:
        return b""
    if not isinstance(value, str):
        raise SandboxValidationError(f"{context} is not valid base64")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise SandboxValidationError(f"{context} is not valid base64") from None


def decode_chunk(value: object) -> models.SandboxOutputChunk:
    if not isinstance(value, dict):
        raise SandboxValidationError("Invalid sandbox output chunk")
    return models.SandboxOutputChunk.parse(
        {
            "stream": value.get("stream"),
            "data": decode_base64(value.get("data"), "sandbox output data"),
            "at": value.get("at"),
        },
        "sandbox output chunk",
    )


def encode_chunk(chunk: models.SandboxOutputChunk) -> dict[str, object]:
    wire: dict[str, object] = {
        "stream": chunk.stream,
        "data": base64.b64encode(chunk.data).decode("ascii"),
        "encoding": "base64",
    }
    if chunk.at is not None:
        wire["at"] = chunk.at.isoformat().replace("+00:00", "Z")
    return wire


# --- Sandboxes ----------------------------------------------------------------

_STARTING: typing.Final = frozenset({"PENDING", "STARTING"})


def _start_failed(
    action: SandboxAction, sandbox: models.SandboxInfo
) -> SandboxError:
    detail: dict[str, object] = {"status": sandbox.status}
    if sandbox.error is not None:
        detail["error"] = sandbox.error
    return SandboxError(
        action=action,
        code=SandboxErrorCode.START_FAILED.value,
        message=f"Sandbox entered {sandbox.status} before reaching RUNNING",
        sandbox_id=sandbox.id,
        retryable=False,
        details=[detail],
    )


def _start_timed_out(
    action: SandboxAction, sandbox: models.SandboxInfo, timeout_ms: int
) -> SandboxError:
    return SandboxError(
        action=action,
        code=SandboxErrorCode.START_TIMED_OUT.value,
        message=f"Sandbox did not reach RUNNING within {timeout_ms} milliseconds",
        sandbox_id=sandbox.id,
        retryable=False,
        details=[{"status": sandbox.status, "timeoutMs": timeout_ms}],
    )


def create(
    body: dict[str, object], running_timeout_ms: int | None
) -> Op[models.SandboxInfo]:
    """
    Create a sandbox. With a running timeout, wait for it to reach RUNNING.
    """

    response = yield from _send(
        Request(
            action="create",
            method="POST",
            path="/v2/sandboxes",
            body=body,
            statuses=(200, 201, 202),
        )
    )
    sandbox = models.SandboxInfo.parse(response.data, "sandbox resource")
    if response.status == 201 and sandbox.status != "RUNNING":
        raise SandboxValidationError(
            f"Sandbox Create returned HTTP 201 with status {sandbox.status}"
        )
    if running_timeout_ms is None:
        return sandbox
    try:
        return (
            yield from wait_until_running(sandbox, running_timeout_ms, "create")
        )
    except (SandboxError, SandboxValidationError):
        # A 202 means this request started the sandbox, and the caller gets
        # only an error, so don't leave it running. A 200 returned an existing
        # sandbox, which isn't ours to destroy.
        if response.status == 202:
            try:
                yield from destroy(sandbox.id)
            except (SandboxError, SandboxValidationError):
                pass
        raise


def wait_until_running(
    sandbox: models.SandboxInfo,
    timeout_ms: int,
    action: typing.Literal["create", "waitUntilRunning"] = "waitUntilRunning",
) -> Op[models.SandboxInfo]:
    if sandbox.status == "RUNNING":
        return sandbox
    if sandbox.status not in _STARTING:
        raise _start_failed(action, sandbox)

    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        if time.monotonic() >= deadline:
            raise _start_timed_out(action, sandbox, timeout_ms)

        try:
            response = yield from _send(
                Request(
                    action=action,
                    method="GET",
                    path=sandbox_path(sandbox.id),
                    statuses=(200,),
                    sandbox_id=sandbox.id,
                )
            )
            sandbox = models.SandboxInfo.parse(
                response.data, "sandbox resource"
            )
        except SandboxError as err:
            # Keep polling through transient failures until the deadline.
            if not err.retryable:
                raise

        if sandbox.status == "RUNNING":
            return sandbox
        if sandbox.status not in _STARTING:
            raise _start_failed(action, sandbox)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _start_timed_out(action, sandbox, timeout_ms)
        yield Sleep(min(POLL_INTERVAL_SECONDS, remaining))


def list_sandboxes(
    query: dict[str, str],
) -> Op[models.SandboxListResult[models.SandboxInfo]]:
    response = yield from _send(
        Request(
            action="list",
            method="GET",
            path="/v2/sandboxes",
            query=query,
            statuses=(200,),
        )
    )
    return models.SandboxListResult(
        items=[
            models.SandboxInfo.parse(item, "sandbox resource")
            for item in _list_items(response.data, "sandbox list")
        ],
        page=models.SandboxPage.parse(response.page, "sandbox list page"),
        fetched_at=_fetched_at(response.metadata),
    )


def get_sandbox(
    sandbox_id: str,
    action: SandboxAction = "get",
) -> Op[models.SandboxInfo | None]:
    try:
        response = yield from _send(
            Request(
                action=action,
                method="GET",
                path=sandbox_path(sandbox_id),
                statuses=(200,),
                sandbox_id=sandbox_id,
            )
        )
    except SandboxError as err:
        if err.code == SandboxErrorCode.NOT_FOUND.value:
            return None
        raise
    return models.SandboxInfo.parse(response.data, "sandbox resource")


def exec_command(
    sandbox_id: str,
    spec: dict[str, object],
    timeout_ms: int,
) -> Op[tuple[bytes, bytes, int]]:
    """
    Run a command and wait for it to exit. Returns raw stdout, stderr, and the
    exit code.
    """

    response = yield from _send(
        Request(
            action="exec",
            method="POST",
            path=f"{sandbox_path(sandbox_id)}/exec",
            body={**spec, "timeout": _ms(timeout_ms)},
            statuses=(200,),
            sandbox_id=sandbox_id,
            timeout=timeout_ms / 1000 + _REQUEST_SLACK_SECONDS,
        )
    )
    data = response.data
    if not isinstance(data, dict):
        raise SandboxValidationError("Invalid sandbox exec result")
    exit_code = data.get("exitCode", 0)
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise SandboxValidationError("Invalid sandbox exec result exitCode")
    return (
        decode_base64(data.get("stdout"), "sandbox exec stdout"),
        decode_base64(data.get("stderr"), "sandbox exec stderr"),
        exit_code,
    )


def destroy(sandbox_id: str) -> Op[models.SandboxDestroyResult]:
    response = yield from _send(
        Request(
            action="destroy",
            method="DELETE",
            path=sandbox_path(sandbox_id),
            statuses=(202, 204),
            sandbox_id=sandbox_id,
        )
    )
    if response.status == 204:
        return models.SandboxDestroyResult(status="TERMINATED")
    sandbox = models.SandboxInfo.parse(response.data, "sandbox resource")
    if sandbox.status != "TERMINATING":
        raise SandboxValidationError(
            "Sandbox Destroy returned a resource that is not TERMINATING"
        )
    return models.SandboxDestroyResult(status="TERMINATING", sandbox=sandbox)


def change_state(
    sandbox: models.SandboxInfo,
    action: typing.Literal["pause", "resume"],
    timeout_ms: int,
) -> Op[models.SandboxInfo]:
    """
    Pause or resume, then wait for PAUSED or RUNNING.
    """

    target = "PAUSED" if action == "pause" else "RUNNING"
    response = yield from _send(
        Request(
            action=action,
            method="POST",
            path=f"{sandbox_path(sandbox.id)}/{action}",
            statuses=(200, 201, 202),
            sandbox_id=sandbox.id,
        )
    )
    current = (
        sandbox
        if response.data is None
        else models.SandboxInfo.parse(response.data, "sandbox resource")
    )

    deadline = time.monotonic() + timeout_ms / 1000
    while current.status != target:
        if current.status in ("FAILED", "TERMINATED"):
            raise SandboxError(
                action=action,
                code=SandboxErrorCode.INVALID_REQUEST.value,
                message=f"Sandbox entered {current.status} before reaching {target}",
                sandbox_id=current.id,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SandboxError(
                action=action,
                code=SandboxErrorCode.START_TIMED_OUT.value,
                message=f"Sandbox did not reach {target} within {timeout_ms} milliseconds",
                sandbox_id=current.id,
            )
        yield Sleep(min(POLL_INTERVAL_SECONDS, remaining))
        try:
            got = yield from _send(
                Request(
                    action=action,
                    method="GET",
                    path=sandbox_path(current.id),
                    statuses=(200,),
                    sandbox_id=current.id,
                )
            )
        except SandboxError as err:
            if not err.retryable:
                raise
            continue
        current = models.SandboxInfo.parse(got.data, "sandbox resource")
        if current.id != sandbox.id:
            raise SandboxValidationError(
                "Sandbox lifecycle operation returned an unrelated sandbox"
            )
    return current


# --- Processes ----------------------------------------------------------------


def _process(sandbox_id: str, value: object) -> models.SandboxProcessInfo:
    if not isinstance(value, dict):
        raise SandboxValidationError("Invalid sandbox process resource")
    return models.SandboxProcessInfo.parse(
        {**value, "sandboxId": sandbox_id}, "sandbox process resource"
    )


def start_process(
    sandbox_id: str, spec: dict[str, object]
) -> Op[models.SandboxProcessInfo]:
    response = yield from _send(
        Request(
            action="process.start",
            method="POST",
            path=f"{sandbox_path(sandbox_id)}/processes",
            body=spec,
            statuses=(201,),
            sandbox_id=sandbox_id,
        )
    )
    process = _process(sandbox_id, response.data)
    if process.state != "RUNNING" or process.pid is None:
        raise SandboxValidationError(
            "Sandbox process Start returned a process that is not RUNNING"
        )
    return process


def list_processes(
    sandbox_id: str, query: dict[str, str]
) -> Op[models.SandboxListResult[models.SandboxProcessInfo]]:
    response = yield from _send(
        Request(
            action="process.list",
            method="GET",
            path=f"{sandbox_path(sandbox_id)}/processes",
            query=query,
            statuses=(200,),
            sandbox_id=sandbox_id,
        )
    )
    items = [
        _process(sandbox_id, item)
        for item in _list_items(response.data, "sandbox process list")
    ]
    return models.SandboxListResult(
        items=sorted(items, key=lambda p: p.id),
        page=models.SandboxPage.parse(
            response.page, "sandbox process list page"
        ),
        fetched_at=_fetched_at(response.metadata),
    )


def get_process(
    sandbox_id: str, process_id: str
) -> Op[models.SandboxProcessInfo | None]:
    try:
        response = yield from _send(
            Request(
                action="process.get",
                method="GET",
                path=process_path(sandbox_id, process_id),
                statuses=(200,),
                sandbox_id=sandbox_id,
                process_id=process_id,
            )
        )
    except SandboxError as err:
        if err.code == SandboxErrorCode.PROCESS_NOT_FOUND.value:
            return None
        raise
    return _process(sandbox_id, response.data)


def signal_process(
    process: models.SandboxProcessInfo, signal: int, include_children: bool
) -> Op[None]:
    yield from _send(
        Request(
            action="process.signal",
            method="POST",
            path=f"{process_path(process.sandbox_id, process.id)}/signals",
            body={"signal": signal, "includeChildren": include_children},
            statuses=(204,),
            sandbox_id=process.sandbox_id,
            process_id=process.id,
        )
    )
    return None


_TERMINAL_STATES: typing.Final = frozenset(
    {"EXITED", "KILLED", "FAILED", "LOST"}
)


def wait_process(
    process: models.SandboxProcessInfo, timeout_ms: int
) -> Op[models.SandboxProcessInfo]:
    """
    Wait for a process to stop. The timeout ends the wait, not the process.
    """

    response = yield from _send(
        Request(
            action="process.wait",
            method="POST",
            path=f"{process_path(process.sandbox_id, process.id)}/wait",
            query={"timeout": _ms(timeout_ms)},
            statuses=(200,),
            sandbox_id=process.sandbox_id,
            process_id=process.id,
            timeout=timeout_ms / 1000 + _REQUEST_SLACK_SECONDS,
        )
    )
    data = response.data
    if not isinstance(data, dict) or data.get("state") not in _TERMINAL_STATES:
        raise SandboxValidationError("Invalid sandbox process wait result")
    return process.model_copy(
        update={
            "state": data["state"],
            "exit_code": data.get("exitCode"),
            "termination_signal": data.get("terminationSignal"),
        }
    )


def process_output(
    process: models.SandboxProcessInfo, tail_bytes: int
) -> Op[models.SandboxProcessOutput]:
    response = yield from _send(
        Request(
            action="process.output",
            method="GET",
            path=f"{process_path(process.sandbox_id, process.id)}/output",
            query={"tailBytes": str(tail_bytes)},
            statuses=(200,),
            sandbox_id=process.sandbox_id,
            process_id=process.id,
        )
    )
    data = response.data
    chunks = data.get("chunks") if isinstance(data, dict) else None
    return models.SandboxProcessOutput(
        chunks=tuple(
            decode_chunk(c) for c in _list_items(chunks, "sandbox output")
        )
    )


# --- Snapshots ----------------------------------------------------------------


def create_snapshot(
    sandbox_id: str, name: str | None
) -> Op[models.SandboxSnapshotInfo]:
    response = yield from _send(
        Request(
            action="snapshot.create",
            method="POST",
            path=f"{sandbox_path(sandbox_id)}/snapshots",
            # Unnamed creates send no body at all, not even {}.
            body=None if name is None else {"name": name},
            statuses=(201, 202),
            sandbox_id=sandbox_id,
        )
    )
    snapshot = models.SandboxSnapshotInfo.parse(
        response.data, "sandbox snapshot resource"
    )
    expected = "READY" if response.status == 201 else "CREATING"
    if snapshot.status != expected:
        raise SandboxValidationError(
            f"Sandbox snapshot Create returned HTTP {response.status} with status {snapshot.status}"
        )
    return snapshot


def get_snapshot(
    snapshot_id: str,
    action: SandboxAction = "snapshot.get",
) -> Op[models.SandboxSnapshotInfo | None]:
    try:
        response = yield from _send(
            Request(
                action=action,
                method="GET",
                path=snapshot_path(snapshot_id),
                statuses=(200,),
                snapshot_id=snapshot_id,
            )
        )
    except SandboxError as err:
        if err.code == SandboxErrorCode.SNAPSHOT_NOT_FOUND.value:
            return None
        raise
    return models.SandboxSnapshotInfo.parse(
        response.data, "sandbox snapshot resource"
    )


def _snapshot_not_ready(snapshot: models.SandboxSnapshotInfo) -> SandboxError:
    return SandboxError(
        action="snapshot.waitUntilReady",
        code=SandboxErrorCode.SNAPSHOT_NOT_READY.value,
        message=f"Snapshot entered {snapshot.status} before reaching READY",
        snapshot_id=snapshot.id,
        retryable=False,
        details=[{"status": snapshot.status}],
    )


def wait_until_snapshot_ready(
    snapshot: models.SandboxSnapshotInfo, timeout_ms: int
) -> Op[models.SandboxSnapshotInfo]:
    if snapshot.status == "READY":
        return snapshot
    if snapshot.status != "CREATING":
        raise _snapshot_not_ready(snapshot)

    deadline = time.monotonic() + timeout_ms / 1000

    def timed_out() -> SandboxError:
        return SandboxError(
            action="snapshot.waitUntilReady",
            code=SandboxErrorCode.SNAPSHOT_WAIT_TIMED_OUT.value,
            message=f"Snapshot did not reach READY within {timeout_ms} milliseconds",
            snapshot_id=snapshot.id,
            retryable=False,
            details=[{"status": snapshot.status, "timeoutMs": timeout_ms}],
        )

    while True:
        if time.monotonic() >= deadline:
            raise timed_out()
        try:
            current = yield from get_snapshot(
                snapshot.id, "snapshot.waitUntilReady"
            )
            if current is None:
                raise SandboxError(
                    action="snapshot.waitUntilReady",
                    code=SandboxErrorCode.SNAPSHOT_NOT_FOUND.value,
                    message="Snapshot not found",
                    snapshot_id=snapshot.id,
                )
            snapshot = current
        except SandboxError as err:
            # Keep polling through transient failures until the deadline.
            if not err.retryable:
                raise

        if snapshot.status == "READY":
            return snapshot
        if snapshot.status != "CREATING":
            raise _snapshot_not_ready(snapshot)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise timed_out()
        yield Sleep(min(POLL_INTERVAL_SECONDS, remaining))


def list_snapshots(
    query: dict[str, str],
) -> Op[models.SandboxListResult[models.SandboxSnapshotInfo]]:
    response = yield from _send(
        Request(
            action="snapshot.list",
            method="GET",
            path="/v2/snapshots",
            query=query,
            statuses=(200,),
        )
    )
    return models.SandboxListResult(
        items=[
            models.SandboxSnapshotInfo.parse(item, "sandbox snapshot resource")
            for item in _list_items(response.data, "sandbox snapshot list")
        ],
        page=models.SandboxPage.parse(
            response.page, "sandbox snapshot list page"
        ),
        fetched_at=_fetched_at(response.metadata),
    )


def delete_snapshot(snapshot_id: str) -> Op[None]:
    yield from _send(
        Request(
            action="snapshot.delete",
            method="DELETE",
            path=snapshot_path(snapshot_id),
            statuses=(204,),
            snapshot_id=snapshot_id,
        )
    )
    return None
