from __future__ import annotations

from . import types


class Event(types.BaseModel):
    data: dict[str, object] = {}
    id: str = ""
    name: str
    ts: int = 0
    user: dict[str, object] = {}
