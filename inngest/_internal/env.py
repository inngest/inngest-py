import os
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal


class EnvKey(Enum):
    CF_PAGES = "CF_PAGES"
    CONTEXT = "CONTEXT"
    ENVIRONMENT = "ENVIRONMENT"
    FLASK_ENV = "FLASK_ENV"
    VERCEL_ENV = "VERCEL_ENV"


@dataclass
class _EnvCheck:
    expected: str | None
    key: EnvKey
    operator: Literal["equals", "is_truthy", "starts_with"]


def _equals(key: EnvKey, value: str) -> _EnvCheck:
    return _EnvCheck(expected=value, key=key, operator="equals")


def _is_truthy(key: EnvKey) -> _EnvCheck:
    return _EnvCheck(expected=None, key=key, operator="is_truthy")


def _starts_with(key: EnvKey, value: str) -> _EnvCheck:
    return _EnvCheck(expected=value, key=key, operator="starts_with")


_PROD_CHECKS: Final[list[_EnvCheck]] = [
    _equals(EnvKey.CF_PAGES, "1"),
    _equals(EnvKey.FLASK_ENV, "production"),
    _starts_with(EnvKey.CONTEXT, "prod"),
    _starts_with(EnvKey.ENVIRONMENT, "prod"),
    _starts_with(EnvKey.VERCEL_ENV, "prod"),
]


def is_prod() -> bool:
    for check in _PROD_CHECKS:
        value = os.getenv(check.key.value)
        operator = check.operator
        expected = check.expected

        if value is None:
            continue

        if operator == "equals":
            if value == expected:
                return True
        elif operator == "is_truthy":
            if value:
                return True
        elif operator == "starts_with" and isinstance(expected, str):
            if value.startswith(expected):
                return True

    return False
