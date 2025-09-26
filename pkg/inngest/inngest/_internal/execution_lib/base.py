from __future__ import annotations

import typing

from inngest._internal import types

from .models import (
    CallResult,
    Context,
    ContextSync,
    ReportedStep,
    ReportedStepSync,
)

if typing.TYPE_CHECKING:
    from inngest._internal import (
        client_lib,
        execution_lib,
        function,
        server_lib,
        step_lib,
    )


class BaseExecution(typing.Protocol):
    version: str
    _request: server_lib.ServerRequest

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
        output_type: object = types.EmptySentinel,
    ) -> CallResult: ...


class BaseExecutionSync(typing.Protocol):
    version: str
    _request: server_lib.ServerRequest

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
        output_type: object = types.EmptySentinel,
    ) -> CallResult: ...
