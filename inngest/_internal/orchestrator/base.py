from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, execution, function, step_lib


class BaseOrchestrator(typing.Protocol):
    version: str

    async def report_step(
        self,
        step_info: step_lib.StepInfo,
        inside_parallel: bool,
    ) -> execution.ReportedStep:
        ...

    async def run(
        self,
        client: client_lib.Inngest,
        ctx: execution.Context,
        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ],
        fn: function.Function,
    ) -> execution.CallResult:
        ...


class BaseOrchestratorSync(typing.Protocol):
    version: str

    def run(
        self,
        client: client_lib.Inngest,
        ctx: execution.Context,
        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ],
        fn: function.Function,
    ) -> execution.CallResult:
        ...
