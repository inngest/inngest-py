import datetime
import hashlib
import inspect
import json
import re
import traceback
import typing

import jcs
import pydantic

from inngest._internal import errors, server_lib, types


def get_traceback(err: Exception) -> str:
    return "".join(
        traceback.format_exception(type(err), err, err.__traceback__)
    )


def hash_event_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def hash_signing_key(key: str) -> str:
    return hashlib.sha256(
        bytearray.fromhex(remove_signing_key_prefix(key))
    ).hexdigest()


def hash_step_id(step_id: str) -> str:
    return hashlib.sha1(step_id.encode("utf-8")).hexdigest()  # noqa: S324


def dump_json(obj: object) -> types.MaybeError[str]:
    try:
        return json.dumps(obj)
    except Exception as err:
        return errors.OutputUnserializableError(str(err))


def canonicalize(value: bytes) -> types.MaybeError[bytes]:
    if len(value) == 0:
        return value

    try:
        loaded = json.loads(value)
        value_jcs = jcs.canonicalize(loaded)
        if not isinstance(value_jcs, bytes):
            return Exception("failed to canonicalize")
        return value_jcs
    except Exception as err:
        return Exception("failed to canonicalize: " + str(err))


def remove_signing_key_prefix(key: str) -> str:
    prefix_match = re.match(r"^signkey-[\w]+-", key)
    prefix = ""
    if prefix_match:
        prefix = prefix_match.group(0)

    return key[len(prefix) :]


def deep_strip_none(obj: types.T) -> types.T:
    """
    Recursively remove items whose value is None.
    """

    if isinstance(obj, dict):
        return {k: deep_strip_none(v) for k, v in obj.items() if v is not None}  # type: ignore
    if isinstance(obj, list):
        return [deep_strip_none(v) for v in obj if v is not None]  # type: ignore
    return obj


class _Duration:
    @classmethod
    def second(cls, count: int = 1) -> int:
        return count * 1000

    @classmethod
    def minute(cls, count: int = 1) -> int:
        return count * cls.second(60)

    @classmethod
    def hour(cls, count: int = 1) -> int:
        return count * cls.minute(60)

    @classmethod
    def day(cls, count: int = 1) -> int:
        return count * cls.hour(24)

    @classmethod
    def week(cls, count: int = 1) -> int:
        return count * cls.day(7)


def to_duration_str(
    ms: typing.Union[int, datetime.timedelta],
) -> types.MaybeError[str]:
    if isinstance(ms, datetime.timedelta):
        ms = int(ms.total_seconds() * 1000)

    if ms < _Duration.second():
        return errors.FunctionConfigInvalidError(
            "duration must be at least 1 second"
        )

    if ms < _Duration.minute():
        return f"{ms // _Duration.second()}s"
    if ms < _Duration.hour():
        return f"{ms // _Duration.minute()}m"
    if ms < _Duration.day():
        return f"{ms // _Duration.hour()}h"
    if ms < _Duration.week():
        return f"{ms // _Duration.day()}d"

    return f"{ms // _Duration.week()}w"


def to_maybe_duration_str(
    ms: typing.Union[int, datetime.timedelta, None],
) -> typing.Union[types.MaybeError[str], None]:
    if ms is None:
        return None
    return to_duration_str(ms)


def to_iso_utc(value: datetime.datetime) -> str:
    return (
        value.astimezone(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3]
        + "Z"
    )


def _to_int(value: typing.Any) -> types.MaybeError[int]:
    try:
        return int(value)
    except Exception as err:
        return ValueError(f"invalid integer: {err}")


def get_major_version(version: str) -> types.MaybeError[int]:
    return _to_int(version.split(".")[0])


def get_server_kind(
    headers: dict[str, str],
) -> typing.Union[server_lib.ServerKind, None, Exception]:
    value = headers.get(server_lib.HeaderKey.SERVER_KIND.value, None)
    if value is None:
        return None

    try:
        return server_lib.ServerKind(value)
    except ValueError:
        return Exception(f"invalid server kind: {value}")


async def maybe_await(
    value: typing.Union[types.T, typing.Awaitable[types.T]],
) -> types.T:
    if inspect.isawaitable(value):
        return await value  # type: ignore

    return value  # type: ignore


def remove_first_traceback_frame(err: Exception) -> None:
    """
    Remove the first frame from the traceback, since we don't want our internal
    code to appear in the traceback.
    """

    if err.__traceback__:
        err.__traceback__ = err.__traceback__.tb_next


def serialize_pydantic_output(
    output: object,
    serializer: pydantic.TypeAdapter[typing.Any] | None,
) -> object:
    """
    Serialize function/step Pydantic output to JSON.
    """

    if serializer:
        return serializer.dump_python(output, mode="json")

    return output


def parse_serializer(
    serializer: type[types.T] | pydantic.TypeAdapter[types.T] | None = None,
) -> pydantic.TypeAdapter[types.T] | None:
    """
    Parse a serializer into a model class and a type adapter. This is used to
    parse function/step serializers.
    """

    if serializer is None:
        return None

    if isinstance(serializer, pydantic.TypeAdapter):
        return serializer

    return pydantic.TypeAdapter(serializer)
