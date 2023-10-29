from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import Field, ValidationError, field_serializer

from . import errors, transforms, types


class _BaseConfig(types.BaseModel):
    def convert_validation_error(
        self,
        err: ValidationError,
    ) -> BaseException:
        return errors.InvalidConfig.from_validation_error(err)


class CancelConfig(_BaseConfig):
    event: str
    if_exp: str | None = None
    timeout: int | timedelta | None = None

    @field_serializer("timeout")
    def serialize_timeout(self, value: int | timedelta | None) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class BatchConfig(_BaseConfig):
    max_size: int
    timeout: int | timedelta | None = None

    @field_serializer("timeout")
    def serialize_timeout(self, value: int | timedelta | None) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class FunctionConfig(_BaseConfig):
    batch_events: BatchConfig | None = None
    cancel: CancelConfig | None = None
    id: str
    name: str | None = None
    steps: dict[str, StepConfig]
    throttle: ThrottleConfig | None = None
    triggers: list[TriggerCron | TriggerEvent]

    def _get_url(self) -> str:
        steps = list(self.steps.values())
        if len(steps) == 0:
            raise errors.InvalidConfig("no steps found")
        return list(self.steps.values())[0].runtime.url


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

    @field_serializer("period")
    def serialize_period(self, value: int | timedelta | None) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class TriggerCron(_BaseConfig):
    cron: str


class TriggerEvent(_BaseConfig):
    event: str
    expression: str | None = None
