from __future__ import annotations

from enum import Enum
from typing import Type, TypeVar

from pydantic import BaseModel as _BaseModel
from pydantic import ConfigDict, ValidationError

T = TypeVar("T")

EmptySentinel = object()


class BaseModel(_BaseModel):
    model_config = ConfigDict(strict=True)

    def __init__(  # pylint: disable=no-self-argument
        __pydantic_self__,
        *args: object,
        **kwargs: object,
    ) -> None:
        try:
            super().__init__(*args, **kwargs)
        except ValidationError as err:
            raise __pydantic_self__.convert_validation_error(err) from None

    def convert_validation_error(
        self,
        err: ValidationError,
    ) -> BaseException:
        """
        Subclasses can override this method to convert Pydantic's
        ValidationError into a different error.
        """

        return err

    @classmethod
    def from_dict(
        cls: Type[TBaseModel],
        raw: dict[str, object],
    ) -> TBaseModel:
        return cls.model_validate(raw)

    def to_dict(self) -> dict[str, object]:
        dump = self.model_dump()

        for k, v in dump.items():
            if isinstance(v, BaseModel):
                dump[k] = v.to_dict()
            elif isinstance(v, Enum):
                # Pydantic doesn't serialize enums.
                dump[k] = v.value

        return dump


TBaseModel = TypeVar(  # pylint: disable=invalid-name
    "TBaseModel", bound=BaseModel
)
