from __future__ import annotations

from typing import Final, Literal

from pydantic import Field, ValidationError

from .errors import InvalidConfig
from .types import BaseModel

# A number > 0 followed by a time unit (s, m, h, d, w)
TIME_PERIOD_REGEX: Final = r"^[1-9][0-9]*[s|m|h|d|w]$"


class _BaseConfig(BaseModel):
    def convert_validation_error(
        self,
        err: ValidationError,
    ) -> BaseException:
        return InvalidConfig.from_validation_error(err)


class CancelConfig(_BaseConfig):
    event: str
    if_exp: str | None = None
    timeout: str | None = Field(default=None, pattern=TIME_PERIOD_REGEX)


class BatchConfig(_BaseConfig):
    max_size: int
    timeout: str = Field(pattern=TIME_PERIOD_REGEX)


class FunctionConfig(_BaseConfig):
    batch_events: BatchConfig | None = None
    cancel: CancelConfig | None = None
    id: str
    name: str | None = None
    steps: dict[str, StepConfig]
    throttle: ThrottleConfig | None = None
    triggers: list[TriggerCron | TriggerEvent]


class Runtime(_BaseConfig):
    type: Literal["http"]
    url: str


class StepConfig(_BaseConfig):
    id: str
    name: str
    retries: RetriesConfig | None = None
    runtime: Runtime


class RetriesConfig(_BaseConfig):
    attempts: int = Field(ge=0)


class ThrottleConfig(_BaseConfig):
    key: str | None = None
    count: int
    period: str = Field(pattern=TIME_PERIOD_REGEX)


class TriggerCron(_BaseConfig):
    cron: str


class TriggerEvent(_BaseConfig):
    event: str
    expression: str | None = None
