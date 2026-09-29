from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import typing

from inngest._internal import (
    errors,
    run_context,
    server_lib,
    sessions,
    step_lib,
    types,
)

if typing.TYPE_CHECKING:
    from inngest._internal.deferred import DeferHandle, DeferredParent
    from inngest._internal.scores import ExperimentRef
    from inngest._internal.sessions import EventMeta
    from inngest.experimental.deferred import DeferredFunction


@dataclasses.dataclass
class CallResult:
    error: Exception | None = None

    # Multiple results from a single call (only used for steps). This will only
    # be longer than 1 for parallel steps. Otherwise, it will be 1 long for
    # sequential steps
    multi: list[CallResult] | None = None

    # Need a sentinel value to differentiate between None and unset
    output: object = types.empty_sentinel

    # Step metadata (e.g. user-specified ID)
    step: step_lib.StepInfo | None = None

    @property
    def is_empty(self) -> bool:
        return all(
            [
                self.error is None,
                self.multi is None,
                self.output is types.empty_sentinel,
                self.step is None,
            ]
        )

    @classmethod
    def from_responses(
        cls,
        responses: list[step_lib.StepResponse],
    ) -> CallResult:
        multi = []

        for response in responses:
            error = None
            if isinstance(response.original_error, Exception):
                error = response.original_error

            multi.append(
                cls(
                    error=error,
                    output=response.output,
                    step=response.step,
                )
            )

        return cls(multi=multi)


@dataclasses.dataclass
class Context:
    """
    Async function execution context.

    Attributes:
        attempt: Attempt number (0-indexed). Retries are >= 1.
        event: The event that triggered the function.
        events: The events that triggered the function. Can be >=1 with batching.
        group: Helpers for grouping steps.
        logger: Idempotent logger (wraps client logger).
        job_id: Queue job ID.
        request_id: ID of request sent to SDK.
        run_id: Function run ID.
        sessions: Initialized once from shared triggering-event sessions. Mutable afterward; outgoing sends read its current values.
        step: Step methods.
    """

    attempt: int
    event: server_lib.Event
    events: list[server_lib.Event]
    group: step_lib.Group
    job_id: str | None
    logger: types.Logger
    request_id: str | None
    run_id: str
    step: step_lib.Step
    sessions: dict[str, str] = dataclasses.field(init=False)
    parents: list[DeferredParent] = dataclasses.field(
        default_factory=list, init=False
    )
    _defer_ops: dict[str, step_lib.StepInfo] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )
    _defer_seen: set[str] = dataclasses.field(
        default_factory=set, init=False, repr=False
    )

    def defer(
        self,
        defer_id: str,
        *,
        function: DeferredFunction[typing.Any],
        data: dict[str, object],
        meta: EventMeta | None = None,
        experiment: ExperimentRef | None = None,
    ) -> DeferHandle:
        """Schedule independent work after this run ends; invalid calls log and skip."""
        from inngest._internal import deferred

        return deferred.add(
            self,
            defer_id,
            function=function,
            data=data,
            meta=meta,
            experiment=experiment,
        )

    def __post_init__(self) -> None:
        self.sessions = sessions.get_shared_sessions(self.events)


@dataclasses.dataclass
class ContextSync:
    """
    Sync function execution context.

    Attributes:
        attempt: Attempt number (0-indexed). Retries are >= 1.
        event: The event that triggered the function.
        events: The events that triggered the function. Can be >=1 with batching.
        group: Helpers for grouping steps.
        logger: Idempotent logger (wraps client logger).
        job_id: Queue job ID.
        request_id: ID of request sent to SDK.
        run_id: Function run ID.
        sessions: Initialized once from shared triggering-event sessions. Mutable afterward; outgoing sends read its current values.
        step: Step methods.
    """

    attempt: int
    event: server_lib.Event
    events: list[server_lib.Event]
    group: step_lib.GroupSync
    job_id: str | None
    logger: types.Logger
    request_id: str | None
    run_id: str
    step: step_lib.StepSync
    sessions: dict[str, str] = dataclasses.field(init=False)
    parents: list[DeferredParent] = dataclasses.field(
        default_factory=list, init=False
    )
    _defer_ops: dict[str, step_lib.StepInfo] = dataclasses.field(
        default_factory=dict, init=False, repr=False
    )
    _defer_seen: set[str] = dataclasses.field(
        default_factory=set, init=False, repr=False
    )

    def defer(
        self,
        defer_id: str,
        *,
        function: DeferredFunction[typing.Any],
        data: dict[str, object],
        meta: EventMeta | None = None,
        experiment: ExperimentRef | None = None,
    ) -> DeferHandle:
        """Schedule independent work after this run ends; invalid calls log and skip."""
        from inngest._internal import deferred

        return deferred.add(
            self,
            defer_id,
            function=function,
            data=data,
            meta=meta,
            experiment=experiment,
        )

    def __post_init__(self) -> None:
        self.sessions = sessions.get_shared_sessions(self.events)


FunctionHandlerAsync: typing.TypeAlias = typing.Callable[
    [Context], typing.Awaitable[types.T]
]

FunctionHandlerSync: typing.TypeAlias = typing.Callable[[ContextSync], types.T]


class ReportedStep:
    _current_step_token: contextvars.Token[step_lib.StepInfo | None] | None = (
        None
    )

    def __init__(
        self,
        step_signal: asyncio.Future[ReportedStep],
        step_info: step_lib.StepInfo,
    ) -> None:
        self.error: errors.StepError | None = None
        self.info = step_info
        self.output: object = types.empty_sentinel
        self.skip = False
        self._release_signal = step_signal
        self._done_signal = asyncio.Future[None]()

    async def __aenter__(self) -> ReportedStep:
        if run_context.current_step.get() is not None:
            self.info.op = server_lib.Opcode.STEP_ERROR
            raise step_lib.NestedStepInterrupt()
        self._current_step_token = run_context.current_step.set(self.info)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._current_step_token is None:
            raise errors.UnreachableError("missing current_step token")
        run_context.current_step.reset(self._current_step_token)
        self._done_signal.set_result(None)

    async def release(self) -> None:
        if self._release_signal.done():
            return

        self._release_signal.set_result(self)
        await self._release_signal

    async def release_and_skip(self) -> None:
        self.skip = True
        await self.release()

    def on_done(
        self,
        callback: typing.Callable[[], typing.Coroutine[None, None, None]],
    ) -> None:
        self._done_signal.add_done_callback(
            lambda _: asyncio.create_task(callback())
        )

    async def wait(self) -> None:
        await self._done_signal


class ReportedStepSync:
    _current_step_token: contextvars.Token[step_lib.StepInfo | None] | None = (
        None
    )

    def __init__(self, step_info: step_lib.StepInfo) -> None:
        self.error: errors.StepError | None = None
        self.info = step_info
        self.output: object = types.empty_sentinel
        self.skip = False

    def __enter__(self) -> ReportedStepSync:
        if run_context.current_step.get() is not None:
            raise step_lib.NestedStepInterrupt()
        self._current_step_token = run_context.current_step.set(self.info)
        return self

    def __exit__(self, *args: object) -> None:
        if self._current_step_token is None:
            raise errors.UnreachableError("missing current_step token")
        run_context.current_step.reset(self._current_step_token)


class UserError(Exception):
    """
    Wrap an error that occurred in user code.
    """

    def __init__(self, err: Exception) -> None:
        self.err = err
