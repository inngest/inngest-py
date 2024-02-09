from __future__ import annotations

import typing

from . import types


class Event(types.BaseModel):
    data: typing.Mapping[str, types.JSON] = {}
    id: str = ""
    name: str
    ts: int = 0
    user: typing.Mapping[str, types.JSON] = {}


# Necessary because of the recursive JSON type
Event.model_rebuild()
