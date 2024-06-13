from __future__ import annotations

import dataclasses
import typing

from inngest._internal import event_lib, execution, function, step_lib

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

    async def after_memoization(self) -> None:
        """
        After exhausting memoized step data. Always called immediately before
        before_execution.
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

    async def before_memoization(self) -> None:
        """
        Before checking memoized step data. Always called immediately after
        transform_input.
        """
        return None

    async def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """
        return None

    async def before_send_events(self, events: list[event_lib.Event]) -> None:
        """
        Before sending events.
        """
        return None

    async def transform_input(
        self,
        ctx: execution.Context,
        function: function.Function,
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

    def after_memoization(self) -> None:
        """
        After exhausting memoized step data. Always called immediately before
        before_execution.
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

    def before_memoization(self) -> None:
        """
        Before checking memoized step data. Always called immediately after
        transform_input.
        """
        return None

    def before_response(self) -> None:
        """
        After the output has been set and before the response is sent
        back to Inngest. This is where you can perform any final actions before
        the response is sent back to Inngest. Called multiple times per run when
        using steps.
        """
        return None

    def before_send_events(self, events: list[event_lib.Event]) -> None:
        """
        Before sending events.
        """
        return None

    def transform_input(
        self,
        ctx: execution.Context,
        function: function.Function,
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
    ["client_lib.Inngest", object], typing.Union[Middleware, MiddlewareSync]
]


@dataclasses.dataclass
class TransformOutputResult:
    # Mutations to these fields within middleware will be kept after running
    # middleware
    error: typing.Optional[Exception]
    output: object

    # Mutations to these fields within middleware will be discarded after
    # running middleware
    step: typing.Optional[TransformOutputStepInfo]


@dataclasses.dataclass
class TransformOutputStepInfo:
    id: str
    op: step_lib.Opcode
    opts: typing.Optional[dict[str, object]]
