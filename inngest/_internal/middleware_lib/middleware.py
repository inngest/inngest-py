from __future__ import annotations

import typing

from inngest._internal import event_lib, execution, function

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib


class Middleware:
    def __init__(self, client: client_lib.Inngest) -> None:
        self._client = client

    async def after_execution(self) -> None:
        """
        After executing new code. Called multiple times per run when using
        steps.
        """
        return None

    async def before_execution(self) -> None:
        """
        Before executing new code. Called multiple times per run when using
        steps.
        """
        return None

    async def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps. Not called for function middleware.
        """
        return None

    async def before_send_events(self, events: list[event_lib.Event]) -> None:
        """
        Before sending events.
        """
        return None

    async def transform_input(
        self,
        ctx: function.Context,
    ) -> function.Context:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """
        return ctx

    async def transform_output(
        self,
        output: execution.Output,
    ) -> execution.Output:
        """
        After a function or step returns. Used to modify the returned data.
        Called multiple times per run when using steps. Not called when an error
        is thrown.
        """
        return output


class MiddlewareSync:
    client: client_lib.Inngest

    def __init__(self, client: client_lib.Inngest) -> None:
        self.client = client

    def after_execution(self) -> None:
        """
        After executing new code. Called multiple times per run when using
        steps.
        """
        return None

    def before_execution(self) -> None:
        """
        Before executing new code. Called multiple times per run when using
        steps.
        """
        return None

    def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps. Not called for function middleware.
        """
        return None

    def before_send_events(self, events: list[event_lib.Event]) -> None:
        """
        Before sending events.
        """
        return None

    def transform_input(
        self,
        ctx: function.Context,
    ) -> function.Context:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """
        return ctx

    def transform_output(
        self,
        output: execution.Output,
    ) -> execution.Output:
        """
        After a function or step returns. Used to modify the returned data.
        Called multiple times per run when using steps. Not called when an error
        is thrown.
        """
        return output


UninitializedMiddleware = typing.Callable[
    # Used a "client_lib.Inngest" string to avoid a circular import
    ["client_lib.Inngest"], typing.Union[Middleware, MiddlewareSync]
]
