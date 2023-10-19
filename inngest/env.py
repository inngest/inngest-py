from dataclasses import dataclass
from typing import Final, Literal
import os


@dataclass
class _EnvCheck:
    key: str
    operator: Literal["equals", "is_truthy", "starts_with"]
    value: str | None


def _equals(key: str, value: str) -> _EnvCheck:
    return _EnvCheck(key=key, operator="equals", value=value)


def _is_truthy(key: str) -> _EnvCheck:
    return _EnvCheck(key=key, operator="is_truthy", value=None)


def _starts_with(key: str, value: str) -> _EnvCheck:
    return _EnvCheck(key=key, operator="starts_with", value=value)


_PROD_CHECKS: Final[list[_EnvCheck]] = [
    _equals("CF_PAGES", "1"),
    _equals("FLASK_ENV", "production"),
    _is_truthy("DENO_DEPLOYMENT_ID"),
    _starts_with("CONTEXT", "prod"),
    _starts_with("ENVIRONMENT", "prod"),
    _starts_with("VERCEL_ENV", "prod"),
]


def allow_dev_server() -> bool:
    for check in _PROD_CHECKS:
        value = os.getenv(check.key)
        if value is None:
            continue

        if check.operator == "equals":
            if value != check.value:
                return False
        elif check.operator == "is_truthy":
            if not value:
                return False
        elif check.operator == "starts_with" and isinstance(check.value, str):
            if not value.startswith(check.value):
                return False

    return True
