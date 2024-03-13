import datetime
import hashlib
import inspect
import json
import re
import traceback
import typing

from . import const, errors, types


def get_traceback(err: Exception) -> str:
    return "".join(
        traceback.format_exception(type(err), err, err.__traceback__)
    )


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


def remove_signing_key_prefix(key: str) -> str:
    prefix_match = re.match(r"^signkey-[\w]+-", key)
    prefix = ""
    if prefix_match:
        prefix = prefix_match.group(0)

    return key[len(prefix) :]


def prep_body(obj: types.T) -> types.T:
    """
    Prep body before sending to the Inngest server. This function will:
    - Remove items whose value is None.
    - Convert keys to camelCase.
    """

    if isinstance(obj, dict):
        return {k: prep_body(v) for k, v in obj.items() if v is not None}  # type: ignore
    if isinstance(obj, list):
        return [prep_body(v) for v in obj if v is not None]  # type: ignore
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


def to_iso_utc(value: datetime.datetime) -> str:
    return (
        value.astimezone(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3]
        + "Z"
    )


def get_server_kind(
    headers: dict[str, str],
) -> typing.Union[const.ServerKind, None, Exception]:
    value = headers.get(const.HeaderKey.SERVER_KIND.value, None)
    if value is None:
        return None

    try:
        return const.ServerKind(value)
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
