from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal
import os


class EnvKey(Enum):
    CF_PAGES = "CF_PAGES"
    CONTEXT = "CONTEXT"
    DENO_DEPLOYMENT_ID = "DENO_DEPLOYMENT_ID"
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
    _is_truthy(EnvKey.DENO_DEPLOYMENT_ID),
    _starts_with(EnvKey.CONTEXT, "prod"),
    _starts_with(EnvKey.ENVIRONMENT, "prod"),
    _starts_with(EnvKey.VERCEL_ENV, "prod"),
]


def allow_dev_server() -> bool:
    for check in _PROD_CHECKS:
        value = os.getenv(check.key.value)
        operator = check.operator
        expected = check.expected

        if value is None:
            continue

        if operator == "equals":
            if value == expected:
                return False
        elif operator == "is_truthy":
            if value:
                return False
        elif operator == "starts_with" and isinstance(expected, str):
            if value.startswith(expected):
                return False

    return True
