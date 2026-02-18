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
    timeout: int | datetime.timedelta | None = None
    key: str | None = None
    if_exp: str | None = pydantic.Field(default=None, serialization_alias="if")

    @pydantic.field_serializer("timeout")
    def serialize_timeout(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Cancel(_BaseConfig):
    event: str
    if_exp: str | None = pydantic.Field(default=None, serialization_alias="if")
    timeout: int | datetime.timedelta | None = None

    @pydantic.field_serializer("timeout")
    def serialize_timeout(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Concurrency(_BaseConfig):
    key: str | None = None
    limit: int
    scope: typing.Literal["account", "env", "fn"] | None = None


class Debounce(_BaseConfig):
    key: str | None = None
    period: int | datetime.timedelta
    timeout: int | datetime.timedelta | None = None

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out

    @pydantic.field_serializer("timeout")
    def serialize_timeout(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class FunctionConfig(_BaseConfig):
    batch_events: Batch | None = pydantic.Field(
        ..., serialization_alias="batchEvents"
    )
    cancel: list[Cancel] | None
    concurrency: list[Concurrency] | None
    debounce: Debounce | None
    id: str
    idempotency: str | None
    name: str | None
    priority: Priority | None
    rate_limit: RateLimit | None = pydantic.Field(
        ..., serialization_alias="rateLimit"
    )
    steps: dict[str, Step]
    throttle: Throttle | None
    timeouts: Timeouts | None
    singleton: Singleton | None
    triggers: list[TriggerCron | TriggerEvent]


class Priority(_BaseConfig):
    run: str


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
    retries: Retries | None = None
    runtime: Runtime


class Throttle(_BaseConfig):
    key: str | None = None
    limit: int
    period: int | datetime.timedelta
    burst: int | None = 1

    @pydantic.field_serializer("period")
    def serialize_period(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Timeouts(_BaseConfig):
    start: int | datetime.timedelta | None = None
    finish: int | datetime.timedelta | None = None

    @pydantic.field_serializer("start")
    def serialize_start(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out

    @pydantic.field_serializer("finish")
    def serialize_finish(
        self,
        value: int | datetime.timedelta | None,
    ) -> str | None:
        if value is None:
            return None
        out = transforms.to_duration_str(value)
        if isinstance(out, Exception):
            raise out
        return out


class Singleton(_BaseConfig):
    key: str | None = None
    mode: typing.Literal["skip", "cancel"]


class TriggerCron(_BaseConfig):
    cron: str


class TriggerEvent(_BaseConfig):
    event: str
    expression: str | None = None


class SynchronizeRequest(types.BaseModel):
    app_name: str = pydantic.Field(..., serialization_alias="appname")
    app_version: str | None = pydantic.Field(
        default=None,
        serialization_alias="appVersion",
    )
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
    app_version: str | None = pydantic.Field(
        default=None,
        serialization_alias="appVersion",
    )
    env: str | None
    framework: Framework
    functions: list[FunctionConfig]
    inspection: AuthenticatedInspection
    platform: str | None
    sdk_author: str = const.AUTHOR
    sdk_language: str = const.LANGUAGE
    sdk_version: str = const.VERSION
    url: str
