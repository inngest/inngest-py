from __future__ import annotations

from enum import Enum

from . import event_lib, types


class Call(types.BaseModel):
    ctx: CallContext
    event: event_lib.Event
    events: list[event_lib.Event]
    steps: dict[str, object]


class CallContext(types.BaseModel):
    attempt: int
    run_id: str
    stack: CallStack


class CallStack(types.BaseModel):
    stack: list[str]


class CallError(types.BaseModel):
    is_retriable: bool
    message: str
    name: str
    stack: str


class CallResponse(types.BaseModel):
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
