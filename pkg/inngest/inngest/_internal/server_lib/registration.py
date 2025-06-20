from __future__ import annotations

import datetime
import typing

import pydantic

from inngest._internal import const, errors, transforms, types

from .consts import DeployType, Framework
from .inspection import AuthenticatedInspection, Capabilities


class _BaseConfig(types.BaseModel):
    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.FunctionConfigInvalidError.from_validation_error(err)


class Batch(_BaseConfig):
    max_size: int = pydantic.Field(..., serialization_alias="maxSize")
    timeout: typing.Union[int, datetime.timedelta, None] = None
    key: typing.Optional[str] = None

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
        ..., serialization_alias="batchEvents"
    )
    cancel: typing.Optional[list[Cancel]]
    concurrency: typing.Optional[list[Concurrency]]
    debounce: typing.Optional[Debounce]
    id: str
    idempotency: typing.Optional[str]
    name: typing.Optional[str]
    priority: typing.Optional[Priority]
    rate_limit: typing.Optional[RateLimit] = pydantic.Field(
        ..., serialization_alias="rateLimit"
    )
    steps: dict[str, Step]
    throttle: typing.Optional[Throttle]
    timeouts: typing.Optional[Timeouts]
    singleton: typing.Optional[Singleton]
    triggers: list[typing.Union[TriggerCron, TriggerEvent]]


class Priority(_BaseConfig):
    run: str


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
    type: typing.Literal["http", "ws"]
    url: str


class Step(_BaseConfig):
    id: str
    name: str
    retries: typing.Optional[Retries] = None
    runtime: Runtime


class Throttle(_BaseConfig):
    key: typing.Optional[str] = None
    limit: int
    period: typing.Union[int, datetime.timedelta]
    burst: typing.Optional[int] = 1

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


class Timeouts(_BaseConfig):
    start: typing.Union[int, datetime.timedelta, None] = None
    finish: typing.Union[int, datetime.timedelta, None] = None

    @pydantic.field_serializer("start")
    def serialize_start(
        self,
        value: typing.Union[int, datetime.timedelta, None],
    ) -> typing.Optional[str]:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out

    @pydantic.field_serializer("finish")
    def serialize_finish(
        self,
        value: typing.Union[int, datetime.timedelta, None],
    ) -> typing.Optional[str]:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Singleton(_BaseConfig):
    key: typing.Optional[str] = None
    mode: typing.Literal["skip", "cancel"]


class TriggerCron(_BaseConfig):
    cron: str


class TriggerEvent(_BaseConfig):
    event: str
    expression: typing.Optional[str] = None


class SynchronizeRequest(types.BaseModel):
    app_name: str = pydantic.Field(..., serialization_alias="appname")
    capabilities: Capabilities = Capabilities()
    deploy_type: DeployType
    framework: Framework
    functions: list[FunctionConfig] = pydantic.Field(min_length=1)
    sdk: str
    url: str
    v: str


class InBandSynchronizeRequest(types.BaseModel):
    url: str


class InBandSynchronizeResponse(types.BaseModel):
    app_id: str
    env: typing.Optional[str]
    framework: Framework
    functions: list[FunctionConfig]
    inspection: AuthenticatedInspection
    platform: typing.Optional[str]
    sdk_author: str = const.AUTHOR
    sdk_language: str = const.LANGUAGE
    sdk_version: str = const.VERSION
    url: str
