import pydantic

from inngest._internal import types


class SendEventsResult(types.BaseModel):
    error: str | None = None
    ids: list[str] = pydantic.Field(default_factory=list)
