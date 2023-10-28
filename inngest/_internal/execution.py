from __future__ import annotations

from enum import Enum

from pydantic import Field

from .event import Event
from .types import BaseModel


class Call(BaseModel):
    ctx: CallContext
    event: Event
    events: list[Event]
    steps: dict[str, object]


class CallContext(BaseModel):
    attempt: int
    run_id: str
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
    display_name: str
    id: str
    name: str
    op: Opcode
    opts: dict[str, object] | None = None


class Opcode(Enum):
    SLEEP = "Sleep"
    STEP = "Step"
    WAIT_FOR_EVENT = "WaitForEvent"
