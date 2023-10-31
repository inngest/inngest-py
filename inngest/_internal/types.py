from __future__ import annotations

import typing

import pydantic

from . import result

T = typing.TypeVar("T")

EmptySentinel = object()


class BaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(strict=True)

    def __init__(  # pylint: disable=no-self-argument
        __pydantic_self__,
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
        Subclasses can override this method to convert Pydantic's
        ValidationError into a different error.
        """

        return err

    @classmethod
    def from_dict(
        cls: typing.Type[BaseModelT],
        raw: dict[str, object],
    ) -> BaseModelT:
        return cls.model_validate(raw)

    def to_dict(self) -> result.Result[dict[str, object], Exception]:
        try:
            return result.Ok(self.model_dump(mode="json"))
        except Exception as err:
            return result.Err(err)


BaseModelT = typing.TypeVar("BaseModelT", bound=BaseModel)
