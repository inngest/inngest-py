from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import Field, ValidationError

from .errors import InvalidConfig
from .transforms import to_duration_str
from .types import BaseModel


class _BaseConfig(BaseModel):
    def convert_validation_error(
        self,
        err: ValidationError,
    ) -> BaseException:
        return InvalidConfig.from_validation_error(err)


class CancelConfig(_BaseConfig):
    event: str
    if_exp: str | None = None
    timeout: int | timedelta | None = None

    def to_dict(self) -> dict[str, object]:
        d = super().to_dict()

        if self.timeout is not None:
            d["timeout"] = to_duration_str(self.timeout)
        return d


class BatchConfig(_BaseConfig):
    max_size: int
    timeout: int | timedelta | None = None

    def to_dict(self) -> dict[str, object]:
        d = super().to_dict()

        if self.timeout is not None:
            d["timeout"] = to_duration_str(self.timeout)
        return d


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
    period: int | timedelta | None = None

    def to_dict(self) -> dict[str, object]:
        d = super().to_dict()

        if self.period is not None:
            d["period"] = to_duration_str(self.period)
        return d


class TriggerCron(_BaseConfig):
    cron: str


class TriggerEvent(_BaseConfig):
    event: str
    expression: str | None = None
