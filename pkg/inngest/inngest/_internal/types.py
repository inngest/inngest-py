from __future__ import annotations

import logging
import typing

import pydantic
import typing_extensions

if typing.TYPE_CHECKING:
    # https://github.com/python/typeshed/issues/7855
    Logger = typing.Union[logging.Logger, logging.LoggerAdapter[logging.Logger]]
else:
    Logger = object

T = typing.TypeVar("T")
TTuple = typing_extensions.TypeVarTuple("TTuple")


class EmptySentinel:
    pass


empty_sentinel = EmptySentinel()


# Ideally this would be recursive, but we can't do that for 2 reasons:
# 1. TypedDict is compatible with Mapping[str, object], but not anything with a
#   more restrictive value type (e.g. Mapping[str, "JSON"])
# 2. Mypy errors with "possible cyclic definition"
JSON = typing_extensions.TypeAliasType(
    "JSON",
    typing.Union[
        bool,
        int,
        float,
        str,
        typing.Mapping[str, object],
        typing.Sequence[object],
        None,
    ],
)


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
    ) -> typing.Union[BaseModelT, Exception]:
        try:
            if isinstance(raw, (str, bytes)):
                raw = cls.model_validate_json(raw)

            return cls.model_validate(raw)
        except Exception as err:
            return err

    def to_dict(self) -> MaybeError[dict[str, object]]:
        try:
            return self.model_dump(by_alias=True, mode="json")
        except Exception as err:
            return err


BaseModelT = typing.TypeVar("BaseModelT", bound=BaseModel)

MaybeError: typing_extensions.TypeAlias = typing.Union[T, Exception]


def is_dict(v: object) -> typing.TypeGuard[dict[object, object]]:
    return isinstance(v, dict)


def is_list(v: object) -> typing.TypeGuard[list[object]]:
    return isinstance(v, list)
