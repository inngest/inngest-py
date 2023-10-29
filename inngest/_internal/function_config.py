from __future__ import annotations

import datetime
import typing

import pydantic

from . import errors, transforms, types


class _BaseConfig(types.BaseModel):
    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.InvalidConfig.from_validation_error(err)


class Batch(_BaseConfig):
    max_size: int
    timeout: int | datetime.timedelta | None = None

    @pydantic.field_serializer("timeout")
    def serialize_timeout(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class Cancel(_BaseConfig):
    event: str
    if_exp: str | None = None
    timeout: int | datetime.timedelta | None = None

    @pydantic.field_serializer("timeout")
    def serialize_timeout(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class Debounce(_BaseConfig):
    key: str | None = None
    period: int | datetime.timedelta

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class FunctionConfig(_BaseConfig):
    batch_events: Batch | None = None
    cancel: list[Cancel] | None = None
    debounce: Debounce | None = None
    id: str
    name: str | None = None
    rate_limit: RateLimit | None = None
    steps: dict[str, Step]
    throttle: Throttle | None = None
    triggers: list[TriggerCron | TriggerEvent]

    def _get_url(self) -> str:
        steps = list(self.steps.values())
        if len(steps) == 0:
            raise errors.InvalidConfig("no steps found")
        return list(self.steps.values())[0].runtime.url


class RateLimit(_BaseConfig):
    key: str | None = None
    limit: int
    period: int | datetime.timedelta

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class Retries(_BaseConfig):
    attempts: int = pydantic.Field(ge=0)


class Runtime(_BaseConfig):
    type: typing.Literal["http"]
    url: str


class Step(_BaseConfig):
    id: str
    name: str
    retries: Retries | None = None
    runtime: Runtime


class Throttle(_BaseConfig):
    key: str | None = None
    count: int
    period: int | datetime.timedelta

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        return transforms.to_duration_str(value)


class TriggerCron(_BaseConfig):
    cron: str


class TriggerEvent(_BaseConfig):
    event: str
    expression: str | None = None
