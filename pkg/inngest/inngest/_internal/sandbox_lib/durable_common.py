"""
Shared pieces of the durable sandbox API (ctx.step.sandbox).

Each durable operation is an ordinary step.run whose handler calls the direct
REST client and returns JSON-safe data for replay. The memoized shapes match
the TypeScript SDK's step results, protocol version 1.
"""

from __future__ import annotations

import base64
import dataclasses
import typing

from inngest._internal import const, errors, run_context

from . import models, ops
from .errors import (
    PROTOCOL_VERSION,
    SandboxAction,
    SandboxError,
    SandboxErrorCode,
    SandboxValidationError,
)
from .transport import UploadData, UploadDataSync

# Marks steps that the SDK runs for the user, like the wait inside snapshot().
SDK_ORIGIN: typing.Final = f"inngest-{const.LANGUAGE}@{const.VERSION}"

# A step records at most 4 MiB, and base64 grows output by a third, so 2 MiB of
# raw output fits with room to spare.
MAX_DURABLE_OUTPUT_BYTES: typing.Final = 2 * 1024 * 1024

_MAX_COMMAND_METADATA_CHARS: typing.Final = 1024

Result: typing.TypeAlias = dict[str, object]


@dataclasses.dataclass
class Call:
    """
    One durable sandbox operation: what it targets, and how to run it.
    """

    action: SandboxAction

    # The SDK method the user called, for the trace.
    method: str

    # Builds a fresh operation generator per attempt.
    op: typing.Callable[[], ops.Op[typing.Any]] | None

    # Converts the operation's value to the memoized result fields.
    to_result: typing.Callable[[typing.Any], Result]

    sandbox_id: str | None = None
    sandbox_name: str | None = None
    source_snapshot_id: str | None = None
    command: list[str] | None = None
    cwd: str | None = None
    process_id: str | None = None
    snapshot_id: str | None = None

    # File uploads stream a body instead of running an operation.
    upload: tuple[str, str, UploadData | UploadDataSync, str | None] | None = (
        None
    )

    display_name: str | None = None
    origin: str | None = None

    # A delete that can't find its target has the outcome the caller wanted.
    not_found_result: Result | None = None


def handle_error(call: Call, err: Exception) -> Result:
    """
    Map an operation failure inside the step handler. Retryable API failures
    retry the step; anything else fails it now. Either way the error's fields
    are stored with the step so a replay can rebuild it.
    """

    if (
        isinstance(err, SandboxError)
        and call.not_found_result is not None
        and err.code
        in (
            SandboxErrorCode.NOT_FOUND.value,
            SandboxErrorCode.SNAPSHOT_NOT_FOUND.value,
        )
    ):
        describe(call, result=call.not_found_result)
        return call.not_found_result

    if isinstance(err, SandboxError):
        describe(call, error_code=err.code)
        if call.action == "destroy":
            _warn(f"Sandbox {call.sandbox_id} couldn't be destroyed: {err}")
        raise errors.StepFailureError(
            err, data=err.to_payload(), is_retriable=err.retryable
        ) from err
    if isinstance(err, SandboxValidationError):
        describe(call, error_code=None)
        raise errors.StepFailureError(
            err, data=err.to_payload(), is_retriable=False
        ) from err
    raise err


def finish(call: Call, value: object) -> Result:
    result: Result = {
        "protocolVersion": PROTOCOL_VERSION,
        "action": call.action,
        **call.to_result(value),
    }
    describe(call, result=result)
    return result


def rebuild_error(err: errors.StepError) -> Exception | None:
    """
    Rebuild the sandbox error stored with a failed step. It won't change on a
    function retry, so the function doesn't retry it.
    """

    rebuilt: SandboxError | SandboxValidationError | None = (
        SandboxError.from_payload(err.data)
        or SandboxValidationError.from_payload(err.data)
    )
    if rebuilt is not None:
        rebuilt.is_retriable = False
    return rebuilt


def check_result(raw: object, action: SandboxAction) -> Result:
    if (
        not isinstance(raw, dict)
        or raw.get("protocolVersion") != PROTOCOL_VERSION
        or raw.get("action") != action
    ):
        raise SandboxValidationError(f"Invalid sandbox {action} step result")
    return typing.cast(Result, raw)


# --- Trace metadata -----------------------------------------------------------


def _command_metadata(argv: list[str]) -> dict[str, object]:
    remaining = _MAX_COMMAND_METADATA_CHARS
    command: list[str] = []
    for argument in argv:
        if remaining <= 0:
            break
        command.append(argument[:remaining])
        remaining -= len(argument)

    md: dict[str, object] = {"command": command}
    # A string command runs as /bin/sh -c "<script>". Show what the user wrote.
    if len(command) == 3 and command[0] == "/bin/sh" and command[1] == "-c":
        md["command_display"] = command[2]
    if remaining < 0 or len(command) < len(argv):
        md["command_truncated"] = True
    return md


def _result_metadata(
    action: SandboxAction, result: Result
) -> dict[str, object]:
    md: dict[str, object] = {}
    sandbox = result.get("sandbox")
    if action in ("create", "get", "waitUntilRunning", "pause", "resume"):
        if isinstance(sandbox, dict):
            md["sandbox_id"] = sandbox.get("id")
            md["sandbox_name"] = sandbox.get("name")
    elif action == "exec":
        res = result.get("result")
        if isinstance(res, dict):
            md["exit_code"] = res.get("exitCode")
            output = res.get("output")
            if isinstance(output, dict) and output.get("truncated") is True:
                md["output_truncated"] = True
    elif action in ("process.start", "process.wait", "process.get"):
        process = result.get("process")
        if isinstance(process, dict):
            if action != "process.get":
                md["process_id"] = process.get("id")
            md["process_state"] = process.get("state")
            md["exit_code"] = process.get("exitCode")
            md["termination_signal"] = process.get("terminationSignal")
    elif action in (
        "snapshot.create",
        "snapshot.waitUntilReady",
        "snapshot.get",
    ):
        snapshot = result.get("snapshot")
        if isinstance(snapshot, dict):
            if action != "snapshot.get":
                md["snapshot_id"] = snapshot.get("id")
            md["snapshot_status"] = snapshot.get("status")
    return md


def describe(
    call: Call,
    *,
    result: Result | None = None,
    error_code: str | None = None,
) -> None:
    """
    Attach inngest.sandbox metadata to the executing step, describing the
    sandbox action for the trace. Mirrors SandboxMetadata in the Inngest
    server. Tracing must never fail the step.
    """

    try:
        step = run_context.current_step.get()
        if step is None:
            return

        values: dict[str, object] = {
            "version": 1,
            "action": call.action,
            "method": call.method,
            "sandbox_id": call.sandbox_id,
            "sandbox_name": call.sandbox_name,
            "source_snapshot_id": call.source_snapshot_id,
            "process_id": call.process_id,
            "snapshot_id": call.snapshot_id,
            "cwd": call.cwd,
        }
        if call.command is not None:
            values.update(_command_metadata(call.command))
        if result is not None:
            values.update(_result_metadata(call.action, result))
        else:
            values["error_code"] = error_code

        step.metadata.append(
            {
                "kind": "inngest.sandbox",
                "scope": "step",
                "op": "merge",
                "values": {k: v for k, v in values.items() if v is not None},
            }
        )
    except Exception:  # noqa: S110
        pass


def _warn(message: str) -> None:
    step = run_context.current_step.get()
    if step is not None:
        step.metadata.append(
            {
                "kind": "inngest.warnings",
                "scope": "step",
                "op": "set",
                "values": {"sdk.sandbox.destroy": message},
            }
        )


# --- Calls --------------------------------------------------------------------


def _sandbox_result(info: models.SandboxInfo | None) -> Result:
    return {"sandbox": None if info is None else info.to_ref()}


def parse_sandbox(result: Result) -> models.SandboxInfo | None:
    raw = result.get("sandbox")
    return None if raw is None else models.SandboxInfo.from_ref(raw)


def parse_process(result: Result) -> models.SandboxProcessInfo | None:
    raw = result.get("process")
    return None if raw is None else models.SandboxProcessInfo.from_ref(raw)


def parse_snapshot(result: Result) -> models.SandboxSnapshotInfo | None:
    raw = result.get("snapshot")
    return None if raw is None else models.SandboxSnapshotInfo.from_ref(raw)


def parse_page(result: Result) -> tuple[models.SandboxPage, str]:
    fetched_at = result.get("fetchedAt")
    return (
        models.SandboxPage.parse(result.get("page"), "sandbox list page"),
        fetched_at if isinstance(fetched_at, str) else "",
    )


def _list_result(key: str) -> typing.Callable[[typing.Any], Result]:
    def to_result(value: typing.Any) -> Result:
        listed = typing.cast(models.SandboxListResult[typing.Any], value)
        return {
            key: [item.to_ref() for item in listed.items],
            "page": listed.page.to_wire(),
            "fetchedAt": listed.fetched_at,
        }

    return to_result


def parse_refs(result: Result, key: str) -> list[object]:
    items = result.get(key)
    if not isinstance(items, list):
        raise SandboxValidationError(f"Invalid sandbox {key} step result")
    return items


def create_call(
    body: dict[str, object], running_timeout_ms: int | None
) -> Call:
    return Call(
        action="create",
        method="create",
        op=lambda: ops.create(body, running_timeout_ms),
        to_result=_sandbox_result,
        sandbox_name=typing.cast(str, body["name"]),
        source_snapshot_id=typing.cast("str | None", body.get("snapshotId")),
    )


def list_call(query: dict[str, str]) -> Call:
    return Call(
        action="list",
        method="list",
        op=lambda: ops.list_sandboxes(query),
        to_result=_list_result("sandboxes"),
    )


def get_call(sandbox_id: str) -> Call:
    return Call(
        action="get",
        method="get",
        op=lambda: ops.get_sandbox(sandbox_id),
        to_result=_sandbox_result,
        sandbox_id=sandbox_id,
    )


def wait_until_running_call(
    sandbox: models.SandboxInfo, timeout_ms: int
) -> Call:
    return Call(
        action="waitUntilRunning",
        method="wait_until_running",
        op=lambda: ops.wait_until_running(sandbox, timeout_ms),
        to_result=_sandbox_result,
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
    )


def change_state_call(
    sandbox: models.SandboxInfo,
    action: typing.Literal["pause", "resume"],
    timeout_ms: int,
) -> Call:
    return Call(
        action=action,
        method=action,
        op=lambda: ops.change_state(sandbox, action, timeout_ms),
        to_result=_sandbox_result,
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
    )


def destroy_call(sandbox: models.SandboxInfo) -> Call:
    return Call(
        action="destroy",
        method="destroy",
        op=lambda: ops.destroy(sandbox.id),
        to_result=lambda value: {
            "result": typing.cast(models.SandboxDestroyResult, value).to_wire()
        },
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
        not_found_result={
            "protocolVersion": PROTOCOL_VERSION,
            "action": "destroy",
            "result": {"status": "TERMINATED", "sandbox": None},
        },
    )


def parse_destroy(result: Result) -> models.SandboxDestroyResult:
    return models.SandboxDestroyResult.from_wire(result.get("result"))


def fit_output(
    stdout: bytes, stderr: bytes
) -> tuple[bytes, bytes, models.SandboxOutputInfo]:
    """
    Keep the end of each stream when output is too large to record. Each
    stream gets half of the budget and gives the part it doesn't use to the
    other stream.
    """

    original = (len(stdout), len(stderr))
    if sum(original) <= MAX_DURABLE_OUTPUT_BYTES:
        return stdout, stderr, models.SandboxOutputInfo()

    share = MAX_DURABLE_OUTPUT_BYTES // 2
    keep_out = min(original[0], share)
    keep_err = min(original[1], share)
    remaining = MAX_DURABLE_OUTPUT_BYTES - keep_out - keep_err
    extra = min(original[0] - keep_out, remaining)
    keep_out += extra
    remaining -= extra
    keep_err += min(original[1] - keep_err, remaining)

    return (
        stdout[len(stdout) - keep_out :],
        stderr[len(stderr) - keep_err :],
        models.SandboxOutputInfo(
            truncated=True,
            strategy="tail",
            original_bytes=models.SandboxStreamBytes(
                stdout=original[0], stderr=original[1]
            ),
            retained_bytes=models.SandboxStreamBytes(
                stdout=keep_out, stderr=keep_err
            ),
        ),
    )


def _exec_result(value: typing.Any) -> Result:
    stdout, stderr, exit_code = typing.cast(tuple[bytes, bytes, int], value)
    stdout, stderr, output = fit_output(stdout, stderr)
    return {
        "result": {
            "stdout": base64.b64encode(stdout).decode("ascii"),
            "stderr": base64.b64encode(stderr).decode("ascii"),
            "encoding": "base64",
            "exitCode": exit_code,
            "output": output.model_dump(
                by_alias=True, mode="json", exclude_none=True
            ),
        }
    }


def exec_call(
    sandbox: models.SandboxInfo,
    spec: dict[str, object],
    timeout_ms: int,
) -> Call:
    cwd = spec.get("cwd")
    return Call(
        action="exec",
        method="commands.run",
        op=lambda: ops.exec_command(sandbox.id, spec, timeout_ms),
        to_result=_exec_result,
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
        command=typing.cast(list[str], spec["command"]),
        cwd=cwd if isinstance(cwd, str) else None,
    )


def parse_exec(result: Result) -> models.SandboxCommandResult:
    res = result.get("result")
    if not isinstance(res, dict):
        raise SandboxValidationError("Invalid sandbox exec step result")
    exit_code = res.get("exitCode")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise SandboxValidationError("Invalid sandbox exec step result")
    return models.SandboxCommandResult(
        stdout=ops.decode_base64(
            res.get("stdout"), "sandbox exec stdout"
        ).decode("utf-8", errors="replace"),
        stderr=ops.decode_base64(
            res.get("stderr"), "sandbox exec stderr"
        ).decode("utf-8", errors="replace"),
        exit_code=exit_code,
        output=models.SandboxOutputInfo.parse(
            res.get("output"), "sandbox exec output"
        ),
    )


def upload_call(
    sandbox: models.SandboxInfo,
    path: str,
    data: bytes | str,
    mode: str | None,
) -> Call:
    return Call(
        action="file.upload",
        method="files.upload",
        op=None,
        to_result=lambda value: {
            "result": typing.cast(
                models.SandboxFileUploadResult, value
            ).model_dump(by_alias=True, mode="json")
        },
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
        upload=(sandbox.id, path, data, mode),
    )


def parse_upload(result: Result) -> models.SandboxFileUploadResult:
    return models.SandboxFileUploadResult.parse(
        result.get("result"), "sandbox file upload step result"
    )


def _process_result(value: typing.Any) -> Result:
    process = typing.cast("models.SandboxProcessInfo | None", value)
    return {"process": None if process is None else process.to_ref()}


def start_process_call(
    sandbox: models.SandboxInfo, spec: dict[str, object]
) -> Call:
    cwd = spec.get("cwd")
    return Call(
        action="process.start",
        method="processes.start",
        op=lambda: ops.start_process(sandbox.id, spec),
        to_result=_process_result,
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
        command=typing.cast(list[str], spec["command"]),
        cwd=cwd if isinstance(cwd, str) else None,
    )


def list_processes_call(
    sandbox: models.SandboxInfo, query: dict[str, str]
) -> Call:
    return Call(
        action="process.list",
        method="processes.list",
        op=lambda: ops.list_processes(sandbox.id, query),
        to_result=_list_result("processes"),
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
    )


def get_process_call(sandbox: models.SandboxInfo, process_id: str) -> Call:
    return Call(
        action="process.get",
        method="processes.get",
        op=lambda: ops.get_process(sandbox.id, process_id),
        to_result=_process_result,
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
        process_id=process_id,
    )


def signal_process_call(
    process: models.SandboxProcessInfo, signal: int, include_children: bool
) -> Call:
    return Call(
        action="process.signal",
        method="process.signal",
        op=lambda: ops.signal_process(process, signal, include_children),
        to_result=lambda _: {"result": None},
        sandbox_id=process.sandbox_id,
        process_id=process.id,
        command=list(process.command),
    )


def wait_process_call(
    process: models.SandboxProcessInfo, timeout_ms: int
) -> Call:
    return Call(
        action="process.wait",
        method="process.wait",
        op=lambda: ops.wait_process(process, timeout_ms),
        to_result=_process_result,
        sandbox_id=process.sandbox_id,
        process_id=process.id,
        command=list(process.command),
    )


def process_output_call(
    process: models.SandboxProcessInfo, tail_bytes: int
) -> Call:
    return Call(
        action="process.output",
        method="process.get_output",
        op=lambda: ops.process_output(process, tail_bytes),
        to_result=lambda value: {
            "result": {
                "chunks": [
                    ops.encode_chunk(chunk)
                    for chunk in typing.cast(
                        models.SandboxProcessOutput, value
                    ).chunks
                ]
            }
        },
        sandbox_id=process.sandbox_id,
        process_id=process.id,
        command=list(process.command),
    )


def parse_output(result: Result) -> models.SandboxProcessOutput:
    res = result.get("result")
    chunks = res.get("chunks") if isinstance(res, dict) else None
    if not isinstance(chunks, list):
        raise SandboxValidationError("Invalid sandbox output step result")
    return models.SandboxProcessOutput(
        chunks=tuple(ops.decode_chunk(chunk) for chunk in chunks)
    )


def _snapshot_result(value: typing.Any) -> Result:
    snapshot = typing.cast("models.SandboxSnapshotInfo | None", value)
    return {"snapshot": None if snapshot is None else snapshot.to_ref()}


def create_snapshot_call(sandbox: models.SandboxInfo, name: str | None) -> Call:
    return Call(
        action="snapshot.create",
        method="snapshot",
        op=lambda: ops.create_snapshot(sandbox.id, name),
        to_result=_snapshot_result,
        sandbox_id=sandbox.id,
        sandbox_name=sandbox.name,
        display_name="Create snapshot",
        origin=SDK_ORIGIN,
    )


def wait_snapshot_call(
    snapshot: models.SandboxSnapshotInfo,
    timeout_ms: int,
    *,
    from_snapshot: bool = False,
) -> Call:
    return Call(
        action="snapshot.waitUntilReady",
        method="snapshot" if from_snapshot else "snapshot.wait_until_ready",
        op=lambda: ops.wait_until_snapshot_ready(snapshot, timeout_ms),
        to_result=_snapshot_result,
        snapshot_id=snapshot.id,
        display_name="Wait for snapshot" if from_snapshot else None,
        origin=SDK_ORIGIN if from_snapshot else None,
    )


def list_snapshots_call(query: dict[str, str]) -> Call:
    return Call(
        action="snapshot.list",
        method="snapshots.list",
        op=lambda: ops.list_snapshots(query),
        to_result=_list_result("snapshots"),
    )


def get_snapshot_call(snapshot_id: str) -> Call:
    return Call(
        action="snapshot.get",
        method="snapshots.get",
        op=lambda: ops.get_snapshot(snapshot_id),
        to_result=_snapshot_result,
        snapshot_id=snapshot_id,
    )


def delete_snapshot_call(snapshot: models.SandboxSnapshotInfo) -> Call:
    return Call(
        action="snapshot.delete",
        method="snapshot.delete",
        op=lambda: ops.delete_snapshot(snapshot.id),
        to_result=lambda _: {"result": None},
        snapshot_id=snapshot.id,
        not_found_result={
            "protocolVersion": PROTOCOL_VERSION,
            "action": "snapshot.delete",
            "result": None,
        },
    )
