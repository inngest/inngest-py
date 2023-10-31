from __future__ import annotations

import enum

from . import errors, event_lib, transforms, types


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
    is_internal: bool
    is_retriable: bool
    message: str
    name: str
    stack: str

    @classmethod
    def from_error(cls, err: Exception) -> CallError:
        return cls(
            is_internal=isinstance(err, errors.InternalError),
            is_retriable=isinstance(err, errors.NonRetriableError) is False,
            message=str(err),
            name=type(err).__name__,
            stack=transforms.get_traceback(err),
        )


class CallResponse(types.BaseModel):
    data: object
    display_name: str
    id: str
    name: str
    op: Opcode
    opts: dict[str, object] | None = None


class Opcode(enum.Enum):
    SLEEP = "Sleep"
    STEP = "Step"
    WAIT_FOR_EVENT = "WaitForEvent"
