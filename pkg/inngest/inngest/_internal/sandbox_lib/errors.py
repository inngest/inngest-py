from __future__ import annotations

import enum
import typing

PROTOCOL_VERSION: typing.Final = 1

SandboxAction = typing.Literal[
    "create",
    "list",
    "get",
    "waitUntilRunning",
    "exec",
    "destroy",
    "pause",
    "resume",
    "process.start",
    "process.list",
    "process.get",
    "process.signal",
    "process.wait",
    "process.output",
    "process.stream",
    "logs.stream",
    "file.upload",
    "file.download",
    "snapshot.create",
    "snapshot.list",
    "snapshot.get",
    "snapshot.waitUntilReady",
    "snapshot.delete",
]

_ACTIONS: typing.Final[frozenset[str]] = frozenset(
    typing.get_args(SandboxAction)
)


class SandboxErrorCode(str, enum.Enum):
    """
    Known values of SandboxError.code. The API can return codes that aren't
    listed here, so SandboxError.code is a plain string.
    """

    ACCESS_DENIED = "access_denied"
    COMPUTE_UNAVAILABLE = "compute_unavailable"
    INTERNAL_ERROR = "internal_error"
    INVALID_FIELD_FORMAT = "invalid_field_format"
    INVALID_REQUEST = "invalid_request"
    MISSING_FIELD = "missing_field"
    OPERATION_AMBIGUOUS = "operation_ambiguous"
    RATE_LIMITED = "rate_limited"
    CONCURRENCY_LIMIT_EXCEEDED = "sandbox_concurrency_limit_exceeded"
    EXEC_OUTPUT_TOO_LARGE = "sandbox_exec_output_too_large"
    EXEC_TIMED_OUT = "sandbox_exec_timed_out"
    FILE_NOT_FOUND = "sandbox_file_not_found"
    FILE_TOO_LARGE = "sandbox_file_too_large"
    IMAGE_NOT_FOUND = "sandbox_image_not_found"
    NAME_TAKEN = "sandbox_name_taken"
    NOT_FOUND = "sandbox_not_found"
    START_FAILED = "sandbox_start_failed"
    START_TIMED_OUT = "sandbox_start_timed_out"
    PROCESS_NOT_FOUND = "sandbox_process_not_found"
    PROCESS_OUTPUT_NOT_RETAINED = "sandbox_process_output_not_retained"
    PROCESS_WAIT_TIMED_OUT = "sandbox_process_wait_timed_out"
    SNAPSHOT_LIMIT_EXCEEDED = "sandbox_snapshot_limit_exceeded"
    SNAPSHOT_NAME_TAKEN = "sandbox_snapshot_name_taken"
    SNAPSHOT_NOT_FOUND = "sandbox_snapshot_not_found"
    SNAPSHOT_NOT_READY = "sandbox_snapshot_not_ready"
    SNAPSHOT_WAIT_TIMED_OUT = "sandbox_snapshot_wait_timed_out"


class SandboxError(Exception):
    """
    EXPERIMENTAL: A failed sandbox operation.

    Branch on code, ambiguous, and retryable rather than the message.

    Attributes:
        action: The operation that failed, like "exec" or "snapshot.create".
        code: Machine-readable code. See SandboxErrorCode for known values.
        message: Human-readable description.
        status: HTTP status of the API response, if one arrived.
        sandbox_id: The sandbox the operation targeted, if any.
        process_id: The process the operation targeted, if any.
        snapshot_id: The snapshot the operation targeted, if any.
        ambiguous: The operation may have taken effect. Check its effects
            before sending it again.
        retryable: The same operation can be sent again safely.
        request_id: The API request ID, for support.
        details: Extra error details from the API.
    """

    def __init__(
        self,
        *,
        action: SandboxAction,
        code: str,
        message: str,
        status: int | None = None,
        sandbox_id: str | None = None,
        process_id: str | None = None,
        snapshot_id: str | None = None,
        ambiguous: bool | None = None,
        retryable: bool = False,
        request_id: str | None = None,
        details: typing.Sequence[typing.Mapping[str, object]] = (),
    ) -> None:
        super().__init__(message)
        self.action: SandboxAction = action
        self.code = code
        self.message = message
        self.status = status
        self.sandbox_id = sandbox_id
        self.process_id = process_id
        self.snapshot_id = snapshot_id
        self.ambiguous = (
            ambiguous
            if ambiguous is not None
            else code == SandboxErrorCode.OPERATION_AMBIGUOUS.value
        )
        self.retryable = retryable
        self.request_id = request_id
        self.details: tuple[typing.Mapping[str, object], ...] = tuple(details)

        # Whether the function should retry when this error escapes it. An
        # error rebuilt from a failed step won't change on retry.
        self.is_retriable = True

    def __str__(self) -> str:
        return f"sandbox {self.action}: {self.message} ({self.code})"

    def to_payload(self) -> dict[str, object]:
        """
        JSON-safe fields, stored with a failed durable step. Matches the
        TypeScript SDK's serialized SandboxError.
        """

        payload: dict[str, object] = {
            "protocolVersion": PROTOCOL_VERSION,
            "action": self.action,
            "code": self.code,
            "message": self.message,
            "ambiguous": self.ambiguous,
            "retryable": self.retryable,
            "details": [dict(d) for d in self.details],
        }
        if self.status is not None:
            payload["status"] = self.status
        if self.sandbox_id is not None:
            payload["sandboxId"] = self.sandbox_id
        if self.process_id is not None:
            payload["processId"] = self.process_id
        if self.snapshot_id is not None:
            payload["snapshotId"] = self.snapshot_id
        if self.request_id is not None:
            payload["requestId"] = self.request_id
        return payload

    @classmethod
    def from_payload(cls, payload: object) -> SandboxError | None:
        if not isinstance(payload, dict):
            return None
        if payload.get("protocolVersion") != PROTOCOL_VERSION:
            return None
        action = payload.get("action")
        code = payload.get("code")
        message = payload.get("message")
        ambiguous = payload.get("ambiguous")
        retryable = payload.get("retryable")
        if (
            not isinstance(action, str)
            or action not in _ACTIONS
            or not isinstance(code, str)
            or not isinstance(message, str)
            or not isinstance(ambiguous, bool)
            or not isinstance(retryable, bool)
        ):
            return None

        raw_details = payload.get("details")
        details = (
            [d for d in raw_details if isinstance(d, dict)]
            if isinstance(raw_details, list)
            else []
        )

        return cls(
            action=typing.cast(SandboxAction, action),
            code=code,
            message=message,
            status=_opt_int(payload.get("status")),
            sandbox_id=_opt_str(payload.get("sandboxId")),
            process_id=_opt_str(payload.get("processId")),
            snapshot_id=_opt_str(payload.get("snapshotId")),
            ambiguous=ambiguous,
            retryable=retryable,
            request_id=_opt_str(payload.get("requestId")),
            details=details,
        )


class SandboxValidationError(ValueError):
    """
    EXPERIMENTAL: Invalid input, rejected before a request is sent, or an
    invalid API response.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

        # Invalid input won't change on a function retry.
        self.is_retriable = False

    def to_payload(self) -> dict[str, object]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "type": "sandbox_validation_error",
            "message": self.message,
        }

    @classmethod
    def from_payload(cls, payload: object) -> SandboxValidationError | None:
        if (
            not isinstance(payload, dict)
            or payload.get("protocolVersion") != PROTOCOL_VERSION
            or payload.get("type") != "sandbox_validation_error"
        ):
            return None
        message = payload.get("message")
        if not isinstance(message, str):
            return None
        return cls(message)


_SAFE_TO_REPEAT: typing.Final[frozenset[SandboxAction]] = frozenset(
    {
        "create",
        "destroy",
        "pause",
        "resume",
        "file.upload",
        "list",
        "get",
        "waitUntilRunning",
        "process.list",
        "process.get",
        "process.wait",
        "process.output",
        "process.stream",
        "logs.stream",
        "file.download",
        "snapshot.list",
        "snapshot.get",
        "snapshot.waitUntilReady",
        "snapshot.delete",
    }
)

_AMBIGUOUS_CODES: typing.Final = frozenset(
    {
        SandboxErrorCode.OPERATION_AMBIGUOUS.value,
        SandboxErrorCode.EXEC_OUTPUT_TOO_LARGE.value,
        SandboxErrorCode.EXEC_TIMED_OUT.value,
    }
)

_AVAILABILITY_CODES: typing.Final = frozenset(
    {
        SandboxErrorCode.COMPUTE_UNAVAILABLE.value,
        SandboxErrorCode.RATE_LIMITED.value,
    }
)


def _transport_failure_message(action: SandboxAction) -> str:
    if action == "create":
        return "The Sandbox Create response was not confirmed. Repeating the same Create request is safe"
    if action == "destroy":
        return "Sandbox teardown may have been accepted. Get the sandbox; repeating Destroy is safe"
    if action == "file.upload":
        return "The sandbox file may have been replaced. Repeating the same upload is safe"
    if action == "exec":
        return "The sandbox command may have run. Inspect its external effects before running it again"
    if action == "process.start":
        return "A sandbox process may be running. List processes and reconcile before starting another"
    if action == "process.signal":
        return "The sandbox process signal may have been delivered. Get or wait for the process before sending another"
    if action == "snapshot.create":
        return "Snapshot creation may have started and a retry may create a second snapshot. Check snapshots.list() before creating another"
    if action == "snapshot.delete":
        return "Snapshot deletion may have started. Repeating Delete is safe"
    return "Compute is temporarily unavailable. Retry this operation"


def _ambiguous_response_message(action: SandboxAction) -> str:
    if action == "create":
        return "A sandbox was created, but its current resource could not be loaded. List sandboxes and reconcile by name before creating another"
    return _transport_failure_message(action)


def transport_failure(
    action: SandboxAction,
    *,
    sent: bool = True,
    sandbox_id: str | None = None,
    process_id: str | None = None,
    snapshot_id: str | None = None,
) -> SandboxError:
    """
    No response arrived. Safe actions can be repeated; anything else may have
    taken effect. A request that was never sent can always be repeated.
    """

    safe = not sent or action in _SAFE_TO_REPEAT
    return SandboxError(
        action=action,
        code=(
            SandboxErrorCode.COMPUTE_UNAVAILABLE.value
            if safe
            else SandboxErrorCode.OPERATION_AMBIGUOUS.value
        ),
        message=(
            _transport_failure_message(action)
            if sent
            else "Could not connect to the sandbox API. Retry this operation"
        ),
        sandbox_id=sandbox_id,
        process_id=process_id,
        snapshot_id=snapshot_id,
        ambiguous=not safe,
        retryable=safe,
    )


def from_api_error(
    action: SandboxAction,
    *,
    status: int,
    code: str,
    message: str,
    sandbox_id: str | None = None,
    process_id: str | None = None,
    snapshot_id: str | None = None,
    request_id: str | None = None,
    details: typing.Sequence[typing.Mapping[str, object]] = (),
) -> SandboxError:
    ambiguous = code in _AMBIGUOUS_CODES
    available = code in _AVAILABILITY_CODES or status in (429, 503)
    if status in (502, 504) and not ambiguous and not available:
        # A gateway error doesn't say whether the request took effect, so
        # treat it like a lost response.
        safe = action in _SAFE_TO_REPEAT
        ambiguous, available = not safe, safe
    return SandboxError(
        action=action,
        code=code,
        message=(
            _ambiguous_response_message(action)
            if code == SandboxErrorCode.OPERATION_AMBIGUOUS.value
            else message
        ),
        status=status,
        sandbox_id=sandbox_id,
        process_id=process_id,
        snapshot_id=snapshot_id,
        ambiguous=ambiguous,
        retryable=not ambiguous and available,
        request_id=request_id,
        details=details,
    )


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _opt_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None
