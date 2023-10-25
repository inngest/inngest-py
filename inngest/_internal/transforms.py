import hashlib
import re
from datetime import datetime, timezone

from .const import Duration
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


def remove_none_deep(obj: T) -> T:
    if isinstance(obj, dict):
        return {k: remove_none_deep(v) for k, v in obj.items() if v is not None}  # type: ignore
    if isinstance(obj, list):
        return [remove_none_deep(v) for v in obj if v is not None]  # type: ignore
    return obj


def to_iso_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        + "Z"
    )


def to_duration_str(ms: int) -> str:
    if ms < Duration.second():
        raise InvalidConfig("duration must be at least 1 second")
    if ms < Duration.minute():
        return f"{ms // Duration.second()}s"
    if ms < Duration.hour():
        return f"{ms // Duration.minute()}m"
    if ms < Duration.day():
        return f"{ms // Duration.hour()}h"
    if ms < Duration.week():
        return f"{ms // Duration.day()}d"

    return f"{ms // Duration.week()}w"
