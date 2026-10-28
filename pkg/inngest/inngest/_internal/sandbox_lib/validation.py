"""
Input validation, ported from the TypeScript and Go SDKs. Invalid input raises
SandboxValidationError before any request is sent.
"""

from __future__ import annotations

import datetime
import json
import re
import typing
import unicodedata

from .errors import SandboxValidationError
from .image import SandboxImage

MAX_PROCESS_TIMEOUT_MS: typing.Final = 5 * 60 * 1000
DEFAULT_PROCESS_TIMEOUT_MS: typing.Final = 30 * 1000
MAX_RUNNING_TIMEOUT_MS: typing.Final = 5 * 60 * 1000
DEFAULT_RUNNING_TIMEOUT_MS: typing.Final = 120 * 1000
MAX_LIFECYCLE_TIMEOUT_MS: typing.Final = 5 * 60 * 1000
MAX_TAIL_BYTES: typing.Final = 512 * 1024
DEFAULT_LIST_LIMIT: typing.Final = 50
MAX_LIST_LIMIT: typing.Final = 250

_MAX_ARGV_COUNT: typing.Final = 128
_MAX_ARGV_BYTES: typing.Final = 32 * 1024
_MAX_ENV_COUNT: typing.Final = 256
_MAX_ENV_BYTES: typing.Final = 64 * 1024
_MAX_PATH_BYTES: typing.Final = 4096
_MAX_SPEC_BYTES: typing.Final = 96 * 1024
_MAX_NAME_CHARACTERS: typing.Final = 255
_MAX_SECRET_NAME_BYTES: typing.Final = 256

_UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
_NIL_UUID: typing.Final = "00000000-0000-0000-0000-000000000000"

# Mirrors the image catalog's names, tags, and artifact digests.
_IMAGE_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_IMAGE_REF = re.compile(
    r"^(?:inngest/)?[a-z0-9][a-z0-9._-]{0,62}"
    r"(?::[a-z0-9][a-z0-9._-]{0,127}|@sha256:[a-f0-9]{64})?$"
)

# encoding/json escapes these. The API measures specs as Go marshals them.
_GO_ESCAPED = re.compile(r"[<>&\u2028\u2029]")

Duration: typing.TypeAlias = "int | datetime.timedelta"


def _utf8_len(value: str, context: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise SandboxValidationError(
            f"{context} must not contain an unpaired surrogate"
        ) from None


def _check_text(value: str, context: str) -> int:
    if "\0" in value:
        raise SandboxValidationError(f"{context} must not contain NUL")
    return _utf8_len(value, context)


def _has_edge_whitespace(value: str) -> bool:
    return value != value.strip()


def validate_name(name: object, field: str = "name") -> str:
    if not isinstance(name, str):
        raise SandboxValidationError(f"{field} must be a string")
    if name == "":
        raise SandboxValidationError(f"{field} must not be empty")
    if len(name) > _MAX_NAME_CHARACTERS:
        raise SandboxValidationError(
            f"{field} must not exceed {_MAX_NAME_CHARACTERS} characters"
        )
    if _has_edge_whitespace(name):
        raise SandboxValidationError(
            f"{field} must not contain leading or trailing whitespace"
        )
    if any(unicodedata.category(c) == "Cc" for c in name):
        raise SandboxValidationError(
            f"{field} must not contain control characters"
        )
    _utf8_len(name, field)
    return name


def _validate_secret_name(name: object) -> str:
    if (
        not isinstance(name, str)
        or name == ""
        or _has_edge_whitespace(name)
        or any(c in name for c in "\r\n\0")
        or _utf8_len(name, "secret name") > _MAX_SECRET_NAME_BYTES
    ):
        raise SandboxValidationError(
            "secrets must be nonempty workspace secret names of at most 256 bytes without leading/trailing whitespace, CR, LF, or NUL"
        )
    return name


def validate_uuid(value: object, field: str) -> str:
    if not isinstance(value, str) or _UUID.match(value) is None:
        raise SandboxValidationError(
            f"{field} must be a canonical lowercase UUID"
        )
    if value == _NIL_UUID:
        raise SandboxValidationError(f"{field} must not be the nil UUID")
    return value


def validate_environment(environment: object) -> dict[str, str]:
    if environment is None:
        return {}
    if not isinstance(environment, typing.Mapping):
        raise SandboxValidationError("environment must be a mapping")
    env: dict[str, str] = {}
    for key, value in environment.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise SandboxValidationError(
                "environment keys and values must be strings"
            )
        env[key] = value
    if len(env) > _MAX_ENV_COUNT:
        raise SandboxValidationError(
            f"environment must not contain more than {_MAX_ENV_COUNT} entries"
        )
    size = 0
    for key, value in env.items():
        if key == "" or "=" in key:
            raise SandboxValidationError(
                "environment keys must be nonempty and must not contain '='"
            )
        size += (
            _check_text(key, f"environment key {key}")
            + 1
            + _check_text(value, f"environment.{key}")
        )
    if size > _MAX_ENV_BYTES:
        raise SandboxValidationError(
            f"environment must not exceed {_MAX_ENV_BYTES} bytes"
        )
    return env


def duration_ms(
    value: object,
    *,
    field: str,
    maximum_ms: int,
    default_ms: int | None = None,
) -> int:
    """
    Convert a timedelta or integer milliseconds to positive milliseconds.
    """

    if value is None:
        if default_ms is None:
            raise SandboxValidationError(f"{field} is required")
        return default_ms

    if isinstance(value, datetime.timedelta):
        ms = value // datetime.timedelta(milliseconds=1)
    elif isinstance(value, int) and not isinstance(value, bool):
        ms = value
    else:
        raise SandboxValidationError(
            f"{field} must be a datetime.timedelta or integer milliseconds"
        )

    if ms <= 0:
        raise SandboxValidationError(f"{field} must be positive")
    if ms > maximum_ms:
        raise SandboxValidationError(
            f"{field} must not exceed {maximum_ms} milliseconds"
        )
    return ms


def normalize_command(command: object) -> list[str]:
    """
    A string runs through /bin/sh -c. A sequence of strings runs as an argv,
    with no shell.
    """

    if isinstance(command, str):
        if command == "":
            raise SandboxValidationError("command must not be empty")
        argv = ["/bin/sh", "-c", command]
        contexts = ["command", "command", "command"]
    elif isinstance(command, (list, tuple)):
        argv = list(command)
        if len(argv) == 0:
            raise SandboxValidationError("command must not be empty")
        if len(argv) > _MAX_ARGV_COUNT:
            raise SandboxValidationError(
                f"command must not contain more than {_MAX_ARGV_COUNT} arguments"
            )
        if not all(isinstance(arg, str) for arg in argv):
            raise SandboxValidationError("command arguments must be strings")
        if argv[0] == "":
            raise SandboxValidationError("command[0] must not be empty")
        contexts = [f"command[{i}]" for i in range(len(argv))]
    else:
        raise SandboxValidationError(
            "command must be a string or a list of strings"
        )

    size = sum(
        _check_text(arg, context)
        for arg, context in zip(argv, contexts, strict=True)
    )
    if size > _MAX_ARGV_BYTES:
        raise SandboxValidationError(
            f"command must not exceed {_MAX_ARGV_BYTES} bytes"
        )
    return argv


def process_spec(
    command: object,
    environment: object,
    cwd: object,
) -> dict[str, object]:
    """
    Validate a command and return its wire spec.
    """

    argv = normalize_command(command)
    env = validate_environment(environment)
    if cwd is not None:
        if not isinstance(cwd, str):
            raise SandboxValidationError("cwd must be a string")
        if _check_text(cwd, "cwd") > _MAX_PATH_BYTES:
            raise SandboxValidationError(
                f"cwd must not exceed {_MAX_PATH_BYTES} bytes"
            )

    measured: dict[str, object] = {"argv": argv}
    if len(env) > 0:
        measured["env"] = env
    if cwd:
        measured["cwd"] = cwd
    encoded = _GO_ESCAPED.sub(
        lambda m: f"\\u{ord(m.group(0)):04x}",
        json.dumps(measured, ensure_ascii=False, separators=(",", ":")),
    )
    if len(encoded.encode("utf-8")) > _MAX_SPEC_BYTES:
        raise SandboxValidationError(
            f"command, environment, and cwd must not exceed {_MAX_SPEC_BYTES} encoded bytes"
        )

    spec: dict[str, object] = {"command": argv}
    if len(env) > 0:
        spec["environment"] = env
    if cwd is not None:
        spec["cwd"] = cwd
    return spec


def validate_image(image: object) -> str:
    ref = image.ref if isinstance(image, SandboxImage) else image
    if not isinstance(ref, str) or not (
        _IMAGE_DIGEST.match(ref)
        if ref.startswith("sha256:")
        # "default" is a legacy alias, not an image you can select.
        else _IMAGE_REF.match(ref) and re.split("[:@]", ref)[0] != "default"
    ):
        raise SandboxValidationError(
            "image must be a published image name[:tag], name@sha256:<hex>, or sha256:<hex>"
        )
    return ref


def create_body(
    *,
    name: object,
    vcpu: object,
    memory_mb: object,
    environment: object,
    secrets: object,
    snapshot_id: object,
    image: object = None,
) -> dict[str, object]:
    validate_name(name)
    body: dict[str, object] = {"name": name}

    if snapshot_id is not None:
        if (
            vcpu is not None
            or memory_mb is not None
            or environment is not None
            or secrets is not None
            or image is not None
        ):
            raise SandboxValidationError(
                "a sandbox created from a snapshot takes its image, resources, environment, and secrets from the snapshot"
            )
        body["snapshotId"] = validate_uuid(snapshot_id, "snapshot_id")
        return body

    for field, value in (("vcpu", vcpu), ("memory_mb", memory_mb)):
        if value is None:
            raise SandboxValidationError(f"{field} is required")
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            or value > 0xFFFFFFFF
        ):
            raise SandboxValidationError(
                f"{field} must be a positive 32-bit integer"
            )
    body["vcpu"] = vcpu
    body["memoryMb"] = memory_mb
    if image is not None:
        body["image"] = validate_image(image)

    env = validate_environment(environment)
    selected: list[str] = []
    if secrets is not None:
        if isinstance(secrets, str) or not isinstance(secrets, typing.Sequence):
            raise SandboxValidationError("secrets must be a list of names")
        for raw in secrets:
            secret = _validate_secret_name(raw)
            if secret in env:
                raise SandboxValidationError(
                    "secrets must not overlap with environment"
                )
            if secret in selected:
                raise SandboxValidationError(
                    "secrets must not contain duplicate names"
                )
            selected.append(secret)

    # Secrets become environment variables, so they count toward its limits.
    validate_environment({**env, **dict.fromkeys(selected, "")})

    if len(env) > 0:
        body["environment"] = env
    if len(selected) > 0:
        body["secrets"] = selected
    return body


def list_query(cursor: object, limit: object) -> dict[str, str]:
    if limit is None:
        limit = DEFAULT_LIST_LIMIT
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit < 1
        or limit > MAX_LIST_LIMIT
    ):
        raise SandboxValidationError(
            f"limit must be between 1 and {MAX_LIST_LIMIT}"
        )
    query = {"limit": str(limit)}
    if cursor is not None:
        if not isinstance(cursor, str) or cursor == "":
            raise SandboxValidationError("cursor must be a nonempty string")
        query["cursor"] = cursor
    return query


def signal_number(signal: object) -> int:
    if isinstance(signal, bool) or not isinstance(signal, int):
        raise SandboxValidationError("signal must be an integer")
    value = int(signal)
    if value < 1 or value > 64:
        raise SandboxValidationError("signal must be between 1 and 64")
    return value


def tail_bytes(value: object) -> int:
    if value is None:
        return 0
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > MAX_TAIL_BYTES
    ):
        raise SandboxValidationError(
            f"tail_bytes must be between 0 and {MAX_TAIL_BYTES}"
        )
    return value


def file_path(path: object) -> str:
    if not isinstance(path, str) or path == "":
        raise SandboxValidationError("path must be a nonempty string")
    if not path.startswith("/"):
        raise SandboxValidationError("path must be absolute")
    if _check_text(path, "path") > _MAX_PATH_BYTES:
        raise SandboxValidationError(
            f"path must not exceed {_MAX_PATH_BYTES} bytes"
        )
    return path


def file_mode(mode: object) -> str | None:
    if mode is None:
        return None
    if (
        not isinstance(mode, int)
        or isinstance(mode, bool)
        or mode < 1
        or mode > 0o777
    ):
        raise SandboxValidationError("mode must be between 0o001 and 0o777")
    return format(mode, "04o")
