from __future__ import annotations

from enum import Enum
from typing import Type, TypeVar

from pydantic import BaseModel as _BaseModel

T = TypeVar("T")

EmptySentinel = object()


class BaseModel(_BaseModel):
    @classmethod
    def from_dict(
        cls: Type[TBaseModel],
        raw: dict[str, object],
    ) -> TBaseModel:
        return cls.model_validate(raw)

    def to_dict(self) -> dict[str, object]:
        dump = self.model_dump(
            # Enable since we want to serialize to aliases.
            by_alias=True,
        )

        for k, v in dump.items():
            # Pydantic doesn't serialize enums.
            if isinstance(v, Enum):
                dump[k] = v.value

        return dump


TBaseModel = TypeVar("TBaseModel", bound=BaseModel)  # pylint: disable=invalid-name
