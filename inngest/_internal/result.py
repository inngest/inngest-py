from __future__ import annotations

import typing

ErrT = typing.TypeVar("ErrT")
OkT = typing.TypeVar("OkT")


class Err(typing.Generic[ErrT]):
    __match_args__ = ("err_value",)
    __slots__ = ("_value",)

    def __init__(self, value: ErrT):
        self._value = value

    @property
    def err_value(self) -> ErrT:
        return self._value

    def is_err(self) -> typing.Literal[True]:
        return True

    def is_ok(self) -> typing.Literal[False]:
        return False


class Ok(typing.Generic[OkT]):
    __match_args__ = ("ok_value",)
    __slots__ = ("_value",)

    def __init__(self, value: OkT):
        self._value = value

    @property
    def ok_value(self) -> OkT:
        return self._value

    def apply_to_ok(self, fn: typing.Callable[[OkT], OkT]) -> Ok[OkT]:
        """
        Apply a transform function to the Ok value and return a new instance of
        Ok.
        """
        return Ok(fn(self.ok_value))

    def is_err(self) -> typing.Literal[False]:
        return False

    def is_ok(self) -> typing.Literal[True]:
        return True


Result: typing.TypeAlias = Ok[OkT] | Err[ErrT]
# MaybeError: typing.TypeAlias = Result[OkT, Exception]
MaybeError: typing.TypeAlias = OkT | Exception


def is_err(result: Result[OkT, ErrT]) -> typing.TypeGuard[Err[ErrT]]:
    return result.is_err()


def is_ok(result: Result[OkT, ErrT]) -> typing.TypeGuard[Ok[OkT]]:
    return result.is_ok()
