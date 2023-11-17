from __future__ import annotations

from inngest._internal import client_lib, function, types

from .middleware import MiddlewareSync


class LoggerProxy:
    _proxied_methods = (
        "critical",
        "debug",
        "error",
        "exception",
        "fatal",
        "info",
        "log",
        "warn",
        "warning",
    )

    def __init__(self, logger: types.Logger) -> None:
        self._is_enabled = False
        self.logger = logger

    def __getattr__(self, name: str) -> object:
        if name in self._proxied_methods and not self._is_enabled:
            # Return noop
            return lambda *args, **kwargs: None

        return getattr(self.logger, name)

    def enable(self) -> None:
        self._is_enabled = True


class LoggerMiddleware(MiddlewareSync):
    def __init__(self, client: client_lib.Inngest) -> None:
        super().__init__(client)
        self.logger = LoggerProxy(client.logger)

    def before_execution(self) -> None:
        self.logger.enable()

    def transform_input(
        self,
        ctx: function.Context,
    ) -> function.Context:
        self.logger.logger = ctx.logger
        ctx.logger = self.logger  # type: ignore
        return ctx
