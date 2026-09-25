from __future__ import annotations

import typing

import pydantic

from inngest._internal import sessions, types


class Event(types.BaseModel):
    data: typing.Mapping[str, types.JSON] = {}
    id: str = ""
    name: str
    ts: int = 0
    meta: sessions.EventMeta | None = None

    @pydantic.field_validator("meta", mode="before")
    @classmethod
    def _normalize_meta(cls, value: object) -> sessions.EventMeta | None:
        return sessions.normalize_meta(value)

    @pydantic.field_validator("data", mode="before")
    @classmethod
    def _ensure_dict(
        cls,
        v: typing.Mapping[str, types.JSON] | None,
    ) -> typing.Mapping[str, types.JSON]:
        """
        Necessary because sometimes event data is sent as null, but we want
        users to interact with data as a dict
        """

        return v or {}


# Necessary because of the recursive JSON type
Event.model_rebuild()
