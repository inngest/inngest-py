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
        return errors.FunctionConfigInvalidError.from_validation_error(err)


class Batch(_BaseConfig):
    max_size: int = pydantic.Field(..., serialization_alias="maxSize")
    timeout: typing.Union[int, datetime.timedelta, None] = None

    @pydantic.field_serializer("timeout")
    def serialize_timeout(
        self,
        value: typing.Union[int, datetime.timedelta, None],
    ) -> typing.Optional[str]:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Cancel(_BaseConfig):
    event: str
    if_exp: typing.Optional[str] = pydantic.Field(
        default=None, serialization_alias="if"
    )
    timeout: typing.Union[int, datetime.timedelta, None] = None

    @pydantic.field_serializer("timeout")
    def serialize_timeout(
        self,
        value: typing.Union[int, datetime.timedelta, None],
    ) -> typing.Optional[str]:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Concurrency(_BaseConfig):
    key: typing.Optional[str] = None
    limit: int
    scope: typing.Optional[typing.Literal["account", "env", "fn"]] = None


class Debounce(_BaseConfig):
    key: typing.Optional[str] = None
    period: typing.Union[int, datetime.timedelta]

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: typing.Union[int, datetime.timedelta, None],
    ) -> typing.Optional[str]:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class FunctionConfig(_BaseConfig):
    batch_events: typing.Optional[Batch] = pydantic.Field(
        default=None, serialization_alias="batchEvents"
    )
    cancel: typing.Optional[list[Cancel]] = None
    concurrency: typing.Optional[list[Concurrency]] = None
    debounce: typing.Optional[Debounce] = None
    id: str
    name: typing.Optional[str] = None
    rate_limit: typing.Optional[RateLimit] = pydantic.Field(
        default=None, serialization_alias="rateLimit"
    )
    steps: dict[str, Step]
    throttle: typing.Optional[Throttle] = None
    triggers: list[typing.Union[TriggerCron, TriggerEvent]]


class RateLimit(_BaseConfig):
    key: typing.Optional[str] = None
    limit: int
    period: typing.Union[int, datetime.timedelta]

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: typing.Union[int, datetime.timedelta, None],
    ) -> typing.Optional[str]:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Retries(_BaseConfig):
    attempts: int = pydantic.Field(ge=0)


class Runtime(_BaseConfig):
    type: typing.Literal["http"]
    url: str


class Step(_BaseConfig):
    id: str
    name: str
    retries: typing.Optional[Retries] = None
    runtime: Runtime


class Throttle(_BaseConfig):
    key: typing.Optional[str] = None
    count: int
    period: typing.Union[int, datetime.timedelta]

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: typing.Union[int, datetime.timedelta, None],
    ) -> typing.Optional[str]:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class TriggerCron(_BaseConfig):
    cron: str


class TriggerEvent(_BaseConfig):
    event: str
    expression: typing.Optional[str] = None
