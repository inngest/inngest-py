from __future__ import annotations

import dataclasses
import typing

from inngest._internal import (
    execution_lib,
    function,
    server_lib,
    step_lib,
    types,
)

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib


class Middleware:
    def __init__(self, client: client_lib.Inngest, raw_request: object) -> None:
        """
        Args:
        ----
            client: Inngest client.
            raw_request: Framework/platform specific request object.
        """

        self.client = client
        self.raw_request = raw_request

    async def after_execution(self) -> None:
        """
        After executing new code. Called multiple times per run when using
        steps.
        """
        return None

    async def after_send_events(
        self,
        result: client_lib.SendEventsResult,
    ) -> None:
        """
        After sending events.
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
        Final cleanup as an invocation unwinds, once execution has started
        (including transform_input). Attempted once per invocation, in registration
        order, even if execution or another middleware hook fails. Cleanup errors
        are logged and do not replace existing execution errors.

        Async task cancellation also attempts cleanup in the same task. A further
        cancellation interrupts only the hook running at that moment; remaining
        hooks still run, then cancellation propagates. Process termination can
        prevent cleanup. A run using steps invokes this hook multiple times.
        """
        return None

    async def before_send_events(self, events: list[server_lib.Event]) -> None:
        """
        Before sending events.
        """
        return None

    async def transform_input(
        self,
        ctx: execution_lib.Context | execution_lib.ContextSync,
        function: function.Function[typing.Any],
        steps: step_lib.StepMemos,
    ) -> None:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """
        return None

    async def transform_output(self, result: TransformOutputResult) -> None:
        """
        After a function or step returns. Used to modify the returned data.
        Called multiple times per run when using steps. Not called when an error
        is thrown.
        """
        return None


class MiddlewareSync:
    client: client_lib.Inngest

    def __init__(self, client: client_lib.Inngest, raw_request: object) -> None:
        """
        Args:
        ----
            client: Inngest client.
            raw_request: Framework/platform specific request object.
        """

        self.client = client
        self.raw_request = raw_request

    def after_execution(self) -> None:
        """
        After executing new code. Called multiple times per run when using
        steps.
        """
        return None

    def after_send_events(
        self,
        result: client_lib.SendEventsResult,
    ) -> None:
        """
        After sending events.
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
        Final cleanup as an invocation unwinds, once execution has started
        (including transform_input). Attempted once per invocation, in registration
        order, even if execution or another middleware hook fails. Cleanup errors
        are logged and do not replace existing execution errors.

        Cancelling a task awaiting a sync worker does not interrupt that worker;
        cleanup runs when its execution unwinds. Process termination can prevent
        cleanup. A run using steps invokes this hook multiple times.
        """
        return None

    def before_send_events(self, events: list[server_lib.Event]) -> None:
        """
        Before sending events.
        """
        return None

    def transform_input(
        self,
        ctx: execution_lib.Context | execution_lib.ContextSync,
        function: function.Function[typing.Any],
        steps: step_lib.StepMemos,
    ) -> None:
        """
        Before calling a function or step. Used to replace certain arguments in
        the function. Called multiple times per run when using steps.
        """
        return None

    def transform_output(self, result: TransformOutputResult) -> None:
        """
        After a function or step returns. Used to modify the returned data.
        Called multiple times per run when using steps. Not called when an error
        is thrown.
        """
        return None


UninitializedMiddleware = typing.Callable[
    # Used a "client_lib.Inngest" string to avoid a circular import
    ["client_lib.Inngest", object], Middleware | MiddlewareSync
]


@dataclasses.dataclass
class TransformOutputResult:
    # Mutations to these fields within middleware will be kept after running
    # middleware
    error: Exception | None
    output: object

    # Mutations to these fields within middleware will be discarded after
    # running middleware
    step: TransformOutputStepInfo | None

    def has_output(self) -> bool:
        return self.output is not types.empty_sentinel


@dataclasses.dataclass
class TransformOutputStepInfo:
    id: str
    op: server_lib.Opcode
    opts: dict[str, object] | None
