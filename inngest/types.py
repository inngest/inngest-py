from __future__ import annotations
import datetime
from enum import Enum
from typing import Callable, Literal, Protocol, TypeVar

from pydantic import BaseModel as _BaseModel, Field


T = TypeVar("T")


class BaseModel(_BaseModel):
    def to_dict(self) -> dict[str, object]:
        dump = self.model_dump(
            # Enable since we want to serialize to aliases.
            by_alias=True,
        )

        for k, v in dump.items():
            # Pydantic doesn't serialize enums.
            if isinstance(v, Enum):
                dump[k] = v.value

        return dump


class ActionError(BaseModel):
    is_retriable: bool
    message: str
    name: str
    stack: str


class ActionResponse(BaseModel):
    data: object

    # Executor expects camelCase.
    display_name: str = Field(
        ...,
        serialization_alias="displayName",
    )
    id: str
    name: str
    op: Opcode


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


class FunctionConfig(BaseModel):
    id: str
    name: str | None = None
    steps: dict[str, StepConfig]
    triggers: list[TriggerCron | TriggerEvent]


class FunctionCall(BaseModel):
    ctx: CallContext
    event: Event
    steps: dict[str, MemoizedStep]

    @staticmethod
    def from_raw(raw: dict) -> FunctionCall:
        ctx = CallContext.from_raw(raw["ctx"])

        steps = {
            step_id: MemoizedStep.from_raw(step)
            for step_id, step in raw["steps"].items()
        }

        return FunctionCall(
            ctx=ctx,
            event=Event.from_raw(raw["event"]),
            steps=steps,
        )


class Event(BaseModel):
    data: dict[str, object] = {}
    id: str = ""
    name: str
    ts: int = 0
    user: dict[str, object] = {}

    @staticmethod
    def from_raw(raw: dict) -> Event:
        return Event(
            data=raw["data"],
            id=raw["id"],
            name=raw["name"],
            ts=raw["ts"],
            user=raw["user"],
        )


class FunctionHandler(Protocol):
    def __call__(self, *, event: Event, step: Step) -> object:
        ...


class MemoizedStep(BaseModel):
    data: object

    @staticmethod
    def from_raw(raw: dict) -> MemoizedStep:
        return MemoizedStep(
            data=raw,
        )


# Opcode = Literal["Sleep", "Step"]
class Opcode(Enum):
    Sleep = "Sleep"
    Step = "Step"


class RegisterRequest(BaseModel):
    app_name: str
    framework: str
    functions: list[FunctionConfig]
    hash: str
    sdk: str
    url: str
    v: str


class Runtime(BaseModel):
    type: Literal["http"]
    url: str


class Step(Protocol):
    def run(
        self,
        id: str,  # pylint: disable=redefined-builtin
        handler: Callable[[], T],
    ) -> T:
        ...

    def send_event(
        self,
        id: str,  # pylint: disable=redefined-builtin
        events: Event | list[Event],
    ) -> list[str]:
        ...

    def sleep_until(
        self,
        id: str,  # pylint: disable=redefined-builtin
        time: datetime.datetime,
    ) -> None:
        ...


class StepConfig(BaseModel):
    id: str
    name: str
    retries: StepConfigRetries | None = None
    runtime: Runtime


class StepConfigRetries(BaseModel):
    attempts: int


class TriggerCron(BaseModel):
    cron: str


class TriggerEvent(BaseModel):
    event: str
    expression: str | None = None
