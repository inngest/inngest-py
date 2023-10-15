from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Literal, Protocol, TypeVar


@dataclass
class ActionResponse:
    data: ActionResponseData
    id: str
    name: str
    op: Op


@dataclass
class ActionResponseData:
    data: object


@dataclass
class FunctionConfig:
    id: str
    steps: dict[str, Step]
    triggers: list[TriggerCron | TriggerEvent]
    name: str | None = None


@dataclass
class FunctionCall:
    event: Event

    @staticmethod
    def from_raw(raw: dict) -> FunctionCall:
        return FunctionCall(
            event=Event.from_raw(raw["event"]),
        )


@dataclass
class Event:
    data: dict[str, object]
    id: str
    name: str
    ts: int
    user: dict[str, object]

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
    def __call__(self, *, event: Event) -> object:
        ...


Op = Literal["Step"]


@dataclass
class RegisterRequest:
    appName: str
    framework: str
    functions: list[FunctionConfig]
    hash: str
    sdk: str
    url: str
    v: str

    def to_dict(self) -> dict[str, object]:
        return remove_none_deep(asdict(self))


T = TypeVar("T")


def remove_none_deep(obj: T) -> T:
    if isinstance(obj, (list, tuple, set)):
        return type(obj)(remove_none_deep(x) for x in obj if x is not None)
    elif isinstance(obj, dict):
        return type(obj)(
            (remove_none_deep(k), remove_none_deep(v))
            for k, v in obj.items()
            if k is not None and v is not None
        )
    else:
        return obj


@dataclass
class Runtime:
    type: Literal["http"]
    url: str


@dataclass
class Step:
    id: str
    name: str
    runtime: Runtime


@dataclass
class TriggerCron:
    cron: str


@dataclass
class TriggerEvent:
    event: str
    expression: str | None = None
