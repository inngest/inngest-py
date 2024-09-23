from __future__ import annotations

import typing

from .models import (
    CallResult,
    Context,
    FunctionHandlerAsync,
    FunctionHandlerSync,
    ReportedStep,
    ReportedStepSync,
)

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, function, step_lib


class BaseExecution(typing.Protocol):
    version: str

    async def report_step(
        self,
        step_info: step_lib.StepInfo,
    ) -> ReportedStep:
        ...

    async def run(
        self,
        client: client_lib.Inngest,
        ctx: Context,
        handler: typing.Union[
            FunctionHandlerAsync,
            FunctionHandlerSync,
        ],
        fn: function.Function,
    ) -> CallResult:
        ...


class BaseExecutionSync(typing.Protocol):
    version: str

    def report_step(
        self,
        step_info: step_lib.StepInfo,
    ) -> ReportedStepSync:
        ...

    def run(
        self,
        client: client_lib.Inngest,
        ctx: Context,
        handler: typing.Union[
            FunctionHandlerAsync,
            FunctionHandlerSync,
        ],
        fn: function.Function,
    ) -> CallResult:
        ...
