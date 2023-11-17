from __future__ import annotations

from . import client_lib, function, middleware_lib, types


class LoggerProxy:
    """
    Wraps a logger, allowing us to disable logging when we want to. This is
    important because we may call a function multiple times and we don't want
    duplicate logs.
    """

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


class LoggerMiddleware(middleware_lib.MiddlewareSync):
    def __init__(self, client: client_lib.Inngest) -> None:
        super().__init__(client)
        self.logger = LoggerProxy(client.logger)

    def before_execution(self) -> None:
        # Enable logging because we've encountered new code.
        self.logger.enable()

    def transform_input(
        self,
        ctx: function.Context,
    ) -> function.Context:
        self.logger.logger = ctx.logger
        ctx.logger = self.logger  # type: ignore
        return ctx
