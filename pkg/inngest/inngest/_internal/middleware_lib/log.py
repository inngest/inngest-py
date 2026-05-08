from __future__ import annotations

import typing

from inngest._internal import (
    client_lib,
    execution_lib,
    function,
    log,
    step_lib,
)

from .middleware import MiddlewareSync


class LoggerMiddleware(MiddlewareSync):
    def __init__(self, client: client_lib.Inngest, raw_request: object) -> None:
        super().__init__(client, raw_request)
        # Start with logging disabled (during step replay)
        log.disable_logging()
        self._filtered_logger: log.FilteredLogger | None = None

    def before_execution(self) -> None:
        # Enable logging when actual execution begins
        log.enable_logging()

    def transform_input(
        self,
        ctx: execution_lib.Context | execution_lib.ContextSync,
        function: function.Function[typing.Any],
        steps: step_lib.StepMemos,
    ) -> None:
        if self._filtered_logger is None:
            self._filtered_logger = log.FilteredLogger(ctx.logger)
        ctx.logger = self._filtered_logger  # type: ignore
