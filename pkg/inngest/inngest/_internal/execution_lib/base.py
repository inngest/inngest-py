from __future__ import annotations

import typing

import pydantic

from inngest._internal import types

from .models import (
    CallResult,
    Context,
    ContextSync,
    ReportedStep,
    ReportedStepSync,
)

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, execution_lib, function, step_lib


class BaseExecution(typing.Protocol):
    version: str

    async def report_step(
        self,
        step_info: step_lib.StepInfo,
    ) -> ReportedStep: ...

    async def run(
        self,
        client: client_lib.Inngest,
        ctx: Context,
        handler: execution_lib.FunctionHandlerAsync[typing.Any],
        fn: function.Function[typing.Any],
        output_serializer: type[typing.Any]
        | pydantic.TypeAdapter[typing.Any]
        | None,
    ) -> CallResult: ...


class BaseExecutionSync(typing.Protocol):
    version: str

    def report_step(
        self,
        step_info: step_lib.StepInfo,
    ) -> ReportedStepSync: ...

    def run(
        self,
        client: client_lib.Inngest,
        ctx: ContextSync,
        handler: execution_lib.FunctionHandlerSync[typing.Any],
        fn: function.Function[typing.Any],
        output_serializer: type[typing.Any]
        | pydantic.TypeAdapter[typing.Any]
        | None,
    ) -> CallResult: ...
