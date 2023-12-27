from __future__ import annotations

import logging
import typing

import pydantic

if typing.TYPE_CHECKING:
    # https://github.com/python/typeshed/issues/7855
    Logger = logging.Logger | logging.LoggerAdapter[logging.Logger]
else:
    Logger = object

T = typing.TypeVar("T")


class EmptySentinel:
    pass


empty_sentinel = EmptySentinel()

Serializable = (
    bool
    | float
    | int
    | str
    | dict[typing.Any, typing.Any]
    | list[typing.Any]
    | tuple[typing.Any, ...]
    | None
)
SerializableT = typing.TypeVar("SerializableT", bound=Serializable)


class BaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(strict=True)

    def __init__(
        __pydantic_self__,  # noqa: N805
        *args: object,
        **kwargs: object,
    ) -> None:
        try:
            super().__init__(*args, **kwargs)
        except pydantic.ValidationError as err:
            raise __pydantic_self__.convert_validation_error(err) from None

    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        """
        Override this method in subclasses to convert Pydantic's
        ValidationError into a different error.
        """
        return err

    @classmethod
    def from_raw(
        cls: type[BaseModelT],
        raw: object,
    ) -> BaseModelT | Exception:
        try:
            return cls.model_validate(raw)
        except Exception as err:
            return err

    def to_dict(self) -> MaybeError[dict[str, object]]:
        try:
            return self.model_dump(by_alias=True, mode="json")
        except Exception as err:
            return err


BaseModelT = typing.TypeVar("BaseModelT", bound=BaseModel)

MaybeError: typing.TypeAlias = T | Exception
