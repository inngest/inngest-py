from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, execution_lib, function, step_lib


class BaseExecution(typing.Protocol):
    version: str

    async def report_step(
        self,
        step_info: step_lib.StepInfo,
        inside_parallel: bool,
    ) -> execution_lib.ReportedStep:
        ...

    async def run(
        self,
        client: client_lib.Inngest,
        ctx: execution_lib.Context,
        handler: typing.Union[
            execution_lib.FunctionHandlerAsync,
            execution_lib.FunctionHandlerSync,
        ],
        fn: function.Function,
    ) -> execution_lib.CallResult:
        ...


class BaseExecutionSync(typing.Protocol):
    version: str

    def run(
        self,
        client: client_lib.Inngest,
        ctx: execution_lib.Context,
        handler: typing.Union[
            execution_lib.FunctionHandlerAsync,
            execution_lib.FunctionHandlerSync,
        ],
        fn: function.Function,
    ) -> execution_lib.CallResult:
        ...
