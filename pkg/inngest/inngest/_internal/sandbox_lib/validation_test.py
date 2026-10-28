from __future__ import annotations

import datetime
import typing

import pytest

from . import durable_common, image, validation
from .errors import SandboxValidationError


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": ""}, "name must not be empty"),
        ({"name": "x" * 256}, "must not exceed 255 characters"),
        ({"name": " job"}, "leading or trailing whitespace"),
        ({"name": "job\n1"}, "control characters"),
        ({"vcpu": None}, "vcpu is required"),
        ({"memory_mb": 0}, "memory_mb must be a positive"),
        ({"vcpu": True}, "vcpu must be a positive"),
        ({"environment": {"A=B": "x"}}, "must not contain '='"),
        ({"environment": {"A": "x\0"}}, "must not contain NUL"),
        ({"secrets": "OPENAI_API_KEY"}, "secrets must be a list"),
        ({"secrets": ["A", "A"]}, "duplicate names"),
        (
            {"environment": {"KEY": "x"}, "secrets": ["KEY"]},
            "must not overlap with environment",
        ),
        (
            {"snapshot_id": "0a8f6c58-1b77-4b5b-9d3e-2f5e7c1a9b10"},
            "takes its image, resources",
        ),
        (
            {
                "snapshot_id": "0a8f6c58-1b77-4b5b-9d3e-2f5e7c1a9b10",
                "vcpu": None,
                "memory_mb": None,
                "image": "my-image",
            },
            "takes its image",
        ),
        (
            {"environment": {f"K{i}": "" for i in range(257)}},
            "more than 256 entries",
        ),
    ],
)
def test_create_body_rejects(
    kwargs: dict[str, typing.Any], message: str
) -> None:
    args: dict[str, typing.Any] = {
        "name": "job",
        "vcpu": 1,
        "memory_mb": 1024,
        "environment": None,
        "secrets": None,
        "snapshot_id": None,
        **kwargs,
    }
    with pytest.raises(SandboxValidationError, match=message):
        validation.create_body(**args)


def test_create_body() -> None:
    assert validation.create_body(
        name="é" * 255,
        vcpu=2,
        memory_mb=2048,
        environment={"A": "1"},
        secrets=["OPENAI_API_KEY"],
        snapshot_id=None,
    ) == {
        "name": "é" * 255,
        "vcpu": 2,
        "memoryMb": 2048,
        "environment": {"A": "1"},
        "secrets": ["OPENAI_API_KEY"],
    }
    assert validation.create_body(
        name="clone",
        vcpu=None,
        memory_mb=None,
        environment=None,
        secrets=None,
        snapshot_id="0a8f6c58-1b77-4b5b-9d3e-2f5e7c1a9b10",
    ) == {"name": "clone", "snapshotId": "0a8f6c58-1b77-4b5b-9d3e-2f5e7c1a9b10"}


@pytest.mark.parametrize(
    ("value", "ref"),
    [
        ("my-image", "my-image"),
        ("my-image:v1.2_3-rc", "my-image:v1.2_3-rc"),
        (
            "my-image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "my-image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        (
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        ("inngest/base:latest", "inngest/base:latest"),
        (image.inngest("base"), "inngest/base"),
        (image.custom("my-image:v1"), "my-image:v1"),
        # Valid names that only start like the reserved alias.
        ("defaults", "defaults"),
        ("x" * 63 + ":" + "t" * 128, "x" * 63 + ":" + "t" * 128),
    ],
)
def test_create_body_image(value: object, ref: str) -> None:
    body = validation.create_body(
        name="job",
        vcpu=1,
        memory_mb=1024,
        environment=None,
        secrets=None,
        snapshot_id=None,
        image=value,
    )
    assert body["image"] == ref


@pytest.mark.parametrize(
    "value",
    [
        "",
        " my-image",
        "my-image ",
        "My-Image",
        "-image",
        "my/image",
        "other/base",
        "x" * 64,
        "my-image:" + "t" * 129,
        "my-image:",
        "my-image@sha256:abc",
        "my-image@sha256:" + "A" * 64,
        "sha256:" + "a" * 63,
        "default",
        "default:latest",
        "default@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "my-image:v1@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        image.custom("Bad"),
        123,
    ],
)
def test_create_body_rejects_image(value: object) -> None:
    with pytest.raises(SandboxValidationError, match="image must be"):
        validation.create_body(
            name="job",
            vcpu=1,
            memory_mb=1024,
            environment=None,
            secrets=None,
            snapshot_id=None,
            image=value,
        )


def test_secrets_count_toward_environment_limit() -> None:
    environment = {f"K{i}": "" for i in range(256)}
    with pytest.raises(SandboxValidationError, match="more than 256 entries"):
        validation.create_body(
            name="job",
            vcpu=1,
            memory_mb=1024,
            environment=environment,
            secrets=["EXTRA"],
            snapshot_id=None,
        )


@pytest.mark.parametrize(
    ("command", "message"),
    [
        ("", "command must not be empty"),
        ([], "command must not be empty"),
        (["", "x"], r"command\[0\] must not be empty"),
        (["a"] * 129, "more than 128 arguments"),
        (["a", 1], "must be strings"),
        (["a", "b\0"], r"command\[1\] must not contain NUL"),
        (["a", "\ud800"], "unpaired surrogate"),
        (["a" * 32 * 1024, "b"], "must not exceed 32768 bytes"),
    ],
)
def test_process_spec_rejects(command: object, message: str) -> None:
    with pytest.raises(SandboxValidationError, match=message):
        validation.process_spec(command, None, None)


def test_process_spec() -> None:
    assert validation.process_spec("ls | wc", None, None) == {
        "command": ["/bin/sh", "-c", "ls | wc"]
    }
    assert validation.process_spec(("ls",), {"A": "1"}, "") == {
        "command": ["ls"],
        "environment": {"A": "1"},
        "cwd": "",
    }


def test_process_spec_measures_encoded_size() -> None:
    # Each part is within its own limit, but together they exceed the 96 KiB
    # spec limit once JSON-encoded. Go escapes "<" as <, six bytes.
    argv = ["<" * 6200]
    environment = {"A": "x" * (60 * 1024)}
    with pytest.raises(SandboxValidationError, match="98304 encoded bytes"):
        validation.process_spec(argv, environment, None)
    # The same sizes without escaped characters fit.
    validation.process_spec(["a" * 6200], environment, None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 30_000),
        (1, 1),
        (datetime.timedelta(minutes=5), 300_000),
        (datetime.timedelta(milliseconds=1500), 1500),
    ],
)
def test_duration(value: object, expected: int) -> None:
    assert (
        validation.duration_ms(
            value, field="timeout", maximum_ms=300_000, default_ms=30_000
        )
        == expected
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (300_001, "must not exceed 300000 milliseconds"),
        (datetime.timedelta(minutes=5, milliseconds=1), "must not exceed"),
        (0, "must be positive"),
        (datetime.timedelta(seconds=-1), "must be positive"),
        (True, "timedelta or integer"),
        (1.5, "timedelta or integer"),
        ("30s", "timedelta or integer"),
    ],
)
def test_duration_rejects(value: object, message: str) -> None:
    with pytest.raises(SandboxValidationError, match=message):
        validation.duration_ms(value, field="timeout", maximum_ms=300_000)


def test_files_and_signals() -> None:
    assert validation.file_mode(0o640) == "0640"
    assert validation.file_mode(None) is None
    for mode in (0, 0o1000, True):
        with pytest.raises(SandboxValidationError):
            validation.file_mode(mode)
    with pytest.raises(SandboxValidationError, match="must be absolute"):
        validation.file_path("app/main.py")
    assert validation.signal_number(9) == 9
    for sig in (0, 65, True):
        with pytest.raises(SandboxValidationError):
            validation.signal_number(sig)
    with pytest.raises(SandboxValidationError):
        validation.tail_bytes(512 * 1024 + 1)
    with pytest.raises(SandboxValidationError):
        validation.list_query(None, 251)


MIB = 1024 * 1024


@pytest.mark.parametrize(
    ("stdout_len", "stderr_len", "kept"),
    [
        # At the limit, nothing is cut.
        (2 * MIB - 10, 10, None),
        # One byte over: stderr is small, so stdout gets the rest.
        (2 * MIB - 9, 10, (2 * MIB - 10, 10)),
        # Both large: each keeps half.
        (3 * MIB, 3 * MIB, (MIB, MIB)),
        # stdout is small, so stderr gets its unused share.
        (100, 3 * MIB, (100, 2 * MIB - 100)),
    ],
)
def test_fit_output(
    stdout_len: int, stderr_len: int, kept: tuple[int, int] | None
) -> None:
    # Distinct leading and trailing bytes show which end was kept.
    stdout = b"H" + b"o" * (stdout_len - 2) + b"T"
    stderr = b"h" + b"e" * (stderr_len - 2) + b"t"
    out, err, info = durable_common.fit_output(stdout, stderr)

    if kept is None:
        assert (out, err) == (stdout, stderr)
        assert info.truncated is False
        return

    assert (len(out), len(err)) == kept
    assert out.endswith(b"T") and err.endswith(b"t")
    assert len(out) + len(err) == 2 * MIB
    assert info.truncated is True
    assert info.strategy == "tail"
    assert info.original_bytes is not None and info.retained_bytes is not None
    assert (info.original_bytes.stdout, info.original_bytes.stderr) == (
        stdout_len,
        stderr_len,
    )
    assert (info.retained_bytes.stdout, info.retained_bytes.stderr) == kept
