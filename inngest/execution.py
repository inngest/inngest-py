from __future__ import annotations

from enum import Enum

from pydantic import Field

from .event import Event
from .types import BaseModel


class Call(BaseModel):
    ctx: CallContext
    event: Event
    steps: dict[str, MemoizedStep]

    @staticmethod
    def from_raw(raw: dict) -> Call:
        ctx = CallContext.from_raw(raw["ctx"])

        steps = {
            step_id: MemoizedStep.from_raw(step)
            for step_id, step in raw["steps"].items()
        }

        return Call(
            ctx=ctx,
            event=Event.from_raw(raw["event"]),
            steps=steps,
        )


class CallContext(BaseModel):
    stack: CallStack

    @staticmethod
    def from_raw(raw: dict) -> CallContext:
        return CallContext(
            stack=CallStack(
                stack=raw["stack"]["stack"],
            ),
        )


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
    display_name: str = Field(
        ...,
        serialization_alias="displayName",
    )
    id: str
    name: str
    op: Opcode


class Opcode(Enum):
    SLEEP = "Sleep"
    STEP = "Step"


class MemoizedStep(BaseModel):
    data: object

    @staticmethod
    def from_raw(raw: dict) -> MemoizedStep:
        return MemoizedStep(
            data=raw,
        )
