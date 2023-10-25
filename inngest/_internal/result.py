from __future__ import annotations

from typing import Generic, Literal, TypeAlias, TypeGuard, TypeVar

E = TypeVar("E")
T = TypeVar("T")


class Ok(Generic[T]):
    def __init__(self, value: T):
        self._value = value

    @property
    def value(self) -> T:
        return self._value

    def is_ok(self) -> Literal[True]:
        return True

    def is_err(self) -> Literal[False]:
        return False


class Err(Generic[E]):
    def __init__(self, value: E):
        self._value = value

    @property
    def value(self) -> E:
        return self._value

    def is_err(self) -> bool:
        return True

    def is_ok(self) -> bool:
        return False


Result: TypeAlias = Ok[T] | Err[E]


def is_err(result: Result[T, E]) -> TypeGuard[Err[E]]:
    return result.is_err()


def is_ok(result: Result[T, E]) -> TypeGuard[Ok[T]]:
    return result.is_ok()
