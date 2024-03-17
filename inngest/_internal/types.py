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


class EmptySentinel:
    pass


empty_sentinel = EmptySentinel()


# Type checking conditional is necessary because of some mutual exclusivity
# between Mypy and Pydantic. Seems like recursive types are finicky right now,
# but hopefully we can simplify this code as support improves
if typing.TYPE_CHECKING:
    # Mypy uses this statically. Pydantic can't use this at runtime since it'll
    # error with "name 'JSON' is not defined"
    JSON = typing.Union[
        bool,
        float,
        int,
        str,
        typing.Mapping[str, "JSON"],
        typing.Sequence["JSON"],
        None,
    ]
else:
    # Pydantic uses this at runtime. Mypy can't use this since it'll error with
    # "possible cyclic definition"
    JSON = typing_extensions.TypeAliasType(
        "JSON",
        typing.Union[
            bool,
            int,
            float,
            str,
            dict[str, "JSON"],
            list["JSON"],
            None,
        ],
    )


JSONT = typing.TypeVar("JSONT", bound=JSON)


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
