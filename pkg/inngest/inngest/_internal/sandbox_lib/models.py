"""
Sandbox resources and results.

Models parse leniently from the REST API, which omits zero values, and dump to
the camelCase "refs" that durable steps memoize. Refs match the TypeScript
SDK's step results.
"""

from __future__ import annotations

import dataclasses
import datetime
import typing

import pydantic
import pydantic.alias_generators

from .errors import SandboxValidationError

SandboxStatus = typing.Literal[
    "PENDING",
    "STARTING",
    "PAUSING",
    "RUNNING",
    "PAUSED",
    "RESUMING",
    "TERMINATING",
    "TERMINATED",
    "FAILED",
]

SandboxProcessState = typing.Literal[
    "STARTING",
    "RUNNING",
    "EXITED",
    "KILLED",
    "FAILED",
    "LOST",
]

SandboxSnapshotStatus = typing.Literal[
    "CREATING",
    "READY",
    "DELETING",
    "DELETED",
    "FAILED",
    "LOST",
]

SandboxOutputStream = typing.Literal["STDOUT", "STDERR"]

ModelT = typing.TypeVar("ModelT", bound="_Model")
T = typing.TypeVar("T")

_SANDBOX_KIND: typing.Final = "inngest/sandbox"
_PROCESS_KIND: typing.Final = "inngest/sandbox.process"
_SNAPSHOT_KIND: typing.Final = "inngest/sandbox.snapshot"
_REF_VERSION: typing.Final = 1


def _empty_to_none(value: object) -> object:
    # The API sends "" or null for unset optional strings.
    return None if value == "" else value


class _Model(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    @classmethod
    def parse(cls: type[ModelT], value: object, context: str) -> ModelT:
        try:
            return cls.model_validate(value)
        except pydantic.ValidationError as err:
            issue = err.errors()[0] if err.error_count() > 0 else None
            where = ""
            message = "validation failed"
            if issue is not None:
                if len(issue["loc"]) > 0:
                    where = " at " + ".".join(str(p) for p in issue["loc"])
                message = issue["msg"]
            raise SandboxValidationError(
                f"Invalid {context}{where}: {message}"
            ) from err

    def _wire(self) -> dict[str, object]:
        return self.model_dump(by_alias=True, mode="json", exclude_none=True)


class SandboxResources(_Model):
    """
    Compute given to a sandbox or recorded in a snapshot.
    """

    vcpu: int
    memory_mb: int


class SandboxInfo(_Model):
    """
    The state of a sandbox when it was last loaded.
    """

    id: str
    name: str
    status: SandboxStatus
    vpc_id: str = ""
    image_ref: str

    # The exact image the sandbox started from, as sha256:<hex>. Unset for
    # sandboxes created before images were pinned.
    image_digest: str | None = None

    resources: SandboxResources
    created_at: datetime.datetime
    started_at: datetime.datetime | None = None
    ended_at: datetime.datetime | None = None

    # Why the sandbox failed, if it did.
    error: str | None = None

    @pydantic.field_validator(
        "error", "image_digest", "started_at", "ended_at", mode="before"
    )
    @classmethod
    def _unset_blank(cls, value: object) -> object:
        return _empty_to_none(value)

    def to_ref(self) -> dict[str, object]:
        return {"kind": _SANDBOX_KIND, "version": _REF_VERSION, **self._wire()}

    @classmethod
    def from_ref(cls, ref: object) -> SandboxInfo:
        _check_ref(ref, _SANDBOX_KIND, "sandbox reference")
        return cls.parse(ref, "sandbox reference")


class SandboxProcessInfo(_Model):
    """
    The state of a background process when it was last loaded.

    exit_code is set only for EXITED processes and termination_signal only for
    KILLED ones.
    """

    sandbox_id: str
    id: str
    command: tuple[str, ...]
    pid: int | None = None
    state: SandboxProcessState
    exit_code: int | None = None
    termination_signal: int | None = None
    started_at: datetime.datetime | None = None
    ended_at: datetime.datetime | None = None

    @pydantic.field_validator("started_at", "ended_at", mode="before")
    @classmethod
    def _unset_blank(cls, value: object) -> object:
        return _empty_to_none(value)

    @property
    def done(self) -> bool:
        """
        Whether the process has stopped.
        """

        return self.state in ("EXITED", "KILLED", "FAILED", "LOST")

    def to_ref(self) -> dict[str, object]:
        return {"kind": _PROCESS_KIND, "version": _REF_VERSION, **self._wire()}

    @classmethod
    def from_ref(cls, ref: object) -> SandboxProcessInfo:
        _check_ref(ref, _PROCESS_KIND, "sandbox process reference")
        return cls.parse(ref, "sandbox process reference")


class SandboxSnapshotInfo(_Model):
    """
    The state of a snapshot when it was last loaded.
    """

    id: str

    # The name given when the snapshot was created, if any.
    name: str | None = None

    source_image_id: str
    status: SandboxSnapshotStatus
    compatibility_id: str | None = None
    resources: SandboxResources
    memory_pack_count: int = 0
    disk_pack_count: int = 0

    # The API may send this 64-bit value as a string.
    stored_bytes: int = 0

    created_at: datetime.datetime
    updated_at: datetime.datetime
    expires_at: datetime.datetime
    error: str | None = None

    @pydantic.field_validator(
        "name", "compatibility_id", "error", mode="before"
    )
    @classmethod
    def _unset_blank(cls, value: object) -> object:
        return _empty_to_none(value)

    def to_ref(self) -> dict[str, object]:
        return {"kind": _SNAPSHOT_KIND, "version": _REF_VERSION, **self._wire()}

    @classmethod
    def from_ref(cls, ref: object) -> SandboxSnapshotInfo:
        _check_ref(ref, _SNAPSHOT_KIND, "sandbox snapshot reference")
        return cls.parse(ref, "sandbox snapshot reference")


class SandboxPage(_Model):
    """
    Where a list result sits in the full list. Pass cursor to the next call to
    read the next page.
    """

    cursor: str | None = None
    has_more: bool = False
    limit: int

    @pydantic.field_validator("cursor", mode="before")
    @classmethod
    def _unset_blank(cls, value: object) -> object:
        return _empty_to_none(value)

    def to_wire(self) -> dict[str, object]:
        return self._wire()


@dataclasses.dataclass(frozen=True)
class SandboxListResult(typing.Generic[T]):
    """
    One page of results.
    """

    items: list[T]
    page: SandboxPage
    fetched_at: str


class SandboxStreamBytes(_Model):
    stdout: int
    stderr: int


class SandboxOutputInfo(_Model):
    """
    Whether command output was cut short. Durable commands keep the end of
    each stream, because failures usually appear at the end.
    """

    truncated: bool = False
    strategy: typing.Literal["tail"] | None = None
    original_bytes: SandboxStreamBytes | None = None
    retained_bytes: SandboxStreamBytes | None = None


class SandboxCommandResult(_Model):
    """
    The outcome of a command that ran to completion. A nonzero exit code is a
    result, not an error.

    stdout and stderr are decoded as UTF-8, with invalid bytes replaced.
    """

    stdout: str
    stderr: str
    exit_code: int
    output: SandboxOutputInfo = SandboxOutputInfo()


class SandboxOutputChunk(_Model):
    """
    One piece of output from a process or the sandbox log.
    """

    model_config = pydantic.ConfigDict(ser_json_bytes="base64")

    stream: SandboxOutputStream
    data: bytes
    at: datetime.datetime | None = None


class SandboxProcessOutput(_Model):
    """
    The retained output of a process.
    """

    chunks: tuple[SandboxOutputChunk, ...] = ()


class SandboxDestroyResult(_Model):
    """
    The outcome of a destroy. sandbox is set only while it is TERMINATING.
    """

    status: typing.Literal["TERMINATING", "TERMINATED"]
    sandbox: SandboxInfo | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "status": self.status,
            "sandbox": None if self.sandbox is None else self.sandbox.to_ref(),
        }

    @classmethod
    def from_wire(cls, value: object) -> SandboxDestroyResult:
        if not isinstance(value, dict):
            raise SandboxValidationError("Invalid sandbox destroy result")
        sandbox = value.get("sandbox")
        return cls.parse(
            {
                "status": value.get("status"),
                "sandbox": None
                if sandbox is None
                else SandboxInfo.from_ref(sandbox),
            },
            "sandbox destroy result",
        )


class SandboxFileUploadResult(_Model):
    path: str
    bytes_written: int = 0


def _check_ref(ref: object, kind: str, context: str) -> None:
    if (
        not isinstance(ref, dict)
        or ref.get("kind") != kind
        or ref.get("version") != _REF_VERSION
    ):
        raise SandboxValidationError(f"Invalid {context}")
