import hashlib
import re
from datetime import datetime, timedelta, timezone

from .errors import InvalidConfig
from .types import T


def hash_signing_key(key: str) -> str:
    return hashlib.sha256(
        bytearray.fromhex(remove_signing_key_prefix(key))
    ).hexdigest()


def hash_step_id(step_id: str) -> str:
    return hashlib.sha1(step_id.encode("utf-8")).hexdigest()


def remove_signing_key_prefix(key: str) -> str:
    prefix_match = re.match(r"^signkey-[\w]+-", key)
    prefix = ""
    if prefix_match:
        prefix = prefix_match.group(0)

    return key[len(prefix) :]


def prep_body(obj: T) -> T:
    """
    Prep body before sending to the Inngest server. This function will:
    - Remove items whose value is None.
    - Convert keys to camelCase.
    """

    if isinstance(obj, dict):
        return {
            to_camel_case(k): prep_body(v)
            for k, v in obj.items()
            if v is not None
        }  # type: ignore
    if isinstance(obj, list):
        return [prep_body(v) for v in obj if v is not None]  # type: ignore
    return obj


def to_camel_case(value: str) -> str:
    """
    Convert a string from snake_case to camelCase.
    """

    return "".join(
        word.title() if i else word for i, word in enumerate(value.split("_"))
    )


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


def to_duration_str(ms: int | timedelta) -> str:
    if isinstance(ms, timedelta):
        ms = int(ms.total_seconds() * 1000)

    if ms < _Duration.second():
        raise InvalidConfig("duration must be at least 1 second")
    if ms < _Duration.minute():
        return f"{ms // _Duration.second()}s"
    if ms < _Duration.hour():
        return f"{ms // _Duration.minute()}m"
    if ms < _Duration.day():
        return f"{ms // _Duration.hour()}h"
    if ms < _Duration.week():
        return f"{ms // _Duration.day()}d"

    return f"{ms // _Duration.week()}w"


def to_iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        + "Z"
    )