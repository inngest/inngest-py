from __future__ import annotations

import typing

from . import types


class Event(types.BaseModel):
    data: typing.Mapping[str, object] = {}
    id: str = ""
    name: str
    ts: int = 0
    user: typing.Mapping[str, object] = {}
