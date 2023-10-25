from __future__ import annotations

from enum import Enum

from pydantic import Field

from .event import Event
from .types import BaseModel


class Call(BaseModel):
    ctx: CallContext
    event: Event
    steps: dict[str, object]


class CallContext(BaseModel):
    stack: CallStack


class CallStack(BaseModel):
    stack: list[str]


class CallError(BaseModel):
    is_retriable: bool
    message: str
    name: str
    stack: str


class CallResponse(BaseModel):
    data: object

    # Executor expects camelCase.
    display_name: str = Field(..., serialization_alias="displayName")
    id: str
    name: str
    op: Opcode
    opts: dict[str, object] | None = None


class Opcode(Enum):
    SLEEP = "Sleep"
    STEP = "Step"
    WAIT_FOR_EVENT = "WaitForEvent"
