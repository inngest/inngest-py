import typing

import pydantic

from inngest._internal import types


class SendEventsResult(types.BaseModel):
    error: typing.Optional[str] = None
    ids: list[str] = pydantic.Field(default_factory=list)
