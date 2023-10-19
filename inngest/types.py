from __future__ import annotations
from dataclasses import asdict, dataclass
import datetime
import enum
from typing import Callable, Literal, Protocol, TypeVar

T = TypeVar("T")

Json = None | bool | float | int | str | dict[str, "Json"] | list["Json"]
TJson = TypeVar("TJson", bound=Json)


@dataclass
class ActionError:
    is_retriable: bool
    message: str
    name: str
    stack: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ActionResponse:
    data: Json
    display_name: str
    id: str
    name: str
    op: Opcode

    def __post_init__(self) -> None:
        if not isinstance(self.display_name, str):
            raise TypeError("display_name must be a string")

        if not isinstance(self.id, str):
            raise TypeError("id must be a string")

        if not isinstance(self.name, str):
            raise TypeError("name must be a string")

        if not isinstance(self.op, Opcode):
            raise ValueError("invalid op")

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)

        data["op"] = data["op"].value

        data["displayName"] = data["display_name"]
        del data["display_name"]

        return data


@dataclass
class CallContext:
    stack: CallStack

    def __post_init__(self) -> None:
        if not isinstance(self.stack, CallStack):
            raise TypeError("stack must be CallStack")

    @staticmethod
    def from_raw(raw: dict) -> CallContext:
        return CallContext(
            stack=CallStack(
                stack=raw["stack"]["stack"],
            ),
        )


@dataclass
class CallStack:
    stack: list[str]

    def __post_init__(self) -> None:
        if not isinstance(self.stack, list):
            raise TypeError("stack must be a list")


@dataclass
class FunctionConfig:
    id: str
    steps: dict[str, StepConfig]
    triggers: list[TriggerCron | TriggerEvent]
    name: str | None = None


@dataclass
class FunctionCall:
    ctx: CallContext
    event: Event
    steps: dict[str, MemoizedStep]

    def __post_init__(self) -> None:
        if not isinstance(self.ctx, CallContext):
            raise TypeError("ctx must be CallContext")

        if not isinstance(self.event, Event):
            raise TypeError("event must be Event")

        if not isinstance(self.steps, dict):
            raise TypeError("steps must be a dict")

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


@dataclass
class Event:
    data: dict[str, object]
    id: str
    name: str
    ts: int
    user: dict[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.data, dict):
            raise TypeError("data must be a dict")

        if not isinstance(self.id, str):
            raise TypeError("id must be a string")

        if not isinstance(self.name, str):
            raise TypeError("name must be a string")

        if not isinstance(self.ts, int):
            raise TypeError("ts must be an int")

        if not isinstance(self.user, dict):
            raise TypeError("user must be a dict")

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


@dataclass
class MemoizedStep:
    data: object

    @staticmethod
    def from_raw(raw: dict) -> MemoizedStep:
        return MemoizedStep(
            data=raw,
        )


# Opcode = Literal["Sleep", "Step"]
class Opcode(enum.Enum):
    Sleep = "Sleep"
    Step = "Step"


@dataclass
class RegisterRequest:
    app_name: str
    framework: str
    functions: list[FunctionConfig]
    hash: str
    sdk: str
    url: str
    v: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["appName"] = data["app_name"]
        del data["app_name"]
        return data


@dataclass
class Runtime:
    type: Literal["http"]
    url: str


class Step(Protocol):
    def run(
        self,
        id: str,  # pylint: disable=redefined-builtin
        handler: Callable[[], TJson],
    ) -> TJson:
        ...

    def sleep_until(
        self,
        id: str,  # pylint: disable=redefined-builtin
        time: datetime.datetime,
    ) -> None:
        ...


@dataclass
class StepConfig:
    id: str
    name: str
    runtime: Runtime
    retries: StepConfigRetries | None = None


@dataclass
class StepConfigRetries:
    attempts: int


@dataclass
class TriggerCron:
    cron: str


@dataclass
class TriggerEvent:
    event: str
    expression: str | None = None
