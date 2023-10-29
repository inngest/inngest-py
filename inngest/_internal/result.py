from __future__ import annotations

import typing

E = typing.TypeVar("E")
T = typing.TypeVar("T")


class Ok(typing.Generic[T]):
    def __init__(self, value: T):
        self._value = value

    @property
    def value(self) -> T:
        return self._value

    def is_ok(self) -> typing.Literal[True]:
        return True

    def is_err(self) -> typing.Literal[False]:
        return False


class Err(typing.Generic[E]):
    def __init__(self, value: E):
        self._value = value

    @property
    def value(self) -> E:
        return self._value

    def is_err(self) -> bool:
        return True

    def is_ok(self) -> bool:
        return False


Result: typing.TypeAlias = Ok[T] | Err[E]


def is_err(result: Result[T, E]) -> typing.TypeGuard[Err[E]]:
    return result.is_err()


def is_ok(result: Result[T, E]) -> typing.TypeGuard[Ok[T]]:
    return result.is_ok()
