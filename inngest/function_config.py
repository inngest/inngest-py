from __future__ import annotations

from typing import Final, Literal

from pydantic import Field

from .types import BaseModel

# A number > 0 followed by a time unit (s, m, h, d, w)
TIME_PERIOD_REGEX: Final = r"^[1-9][0-9]*[s|m|h|d|w]$"


class CancelConfig(BaseModel):
    event: str
    if_expression: str | None = None
    timeout: str | None = Field(default=None, pattern=TIME_PERIOD_REGEX)


class BatchConfig(BaseModel):
    max_size: int
    timeout: str = Field(pattern=TIME_PERIOD_REGEX)


class FunctionConfig(BaseModel):
    batch_events: BatchConfig | None = None
    cancel: CancelConfig | None = None
    id: str
    name: str | None = None
    steps: dict[str, StepConfig]
    throttle: ThrottleConfig | None = None
    triggers: list[TriggerCron | TriggerEvent]


class Runtime(BaseModel):
    type: Literal["http"]
    url: str


class StepConfig(BaseModel):
    id: str
    name: str
    retries: int | None = Field(default=None, gt=0)
    runtime: Runtime

    def to_dict(self) -> dict[str, object]:
        dump = super().to_dict()

        if dump.get("retries") is not None:
            dump["retries"] = {
                "attempts": dump["retries"],
            }

        return dump


class ThrottleConfig(BaseModel):
    key: str | None = None
    count: int
    period: str = Field(pattern=TIME_PERIOD_REGEX)


class TriggerCron(BaseModel):
    cron: str


class TriggerEvent(BaseModel):
    event: str
    expression: str | None = None
