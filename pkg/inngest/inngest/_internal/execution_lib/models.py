from __future__ import annotations

import asyncio
import contextvars
import dataclasses
import typing

from inngest._internal import errors, server_lib, step_lib, types


@dataclasses.dataclass
class CallResult:
    error: typing.Optional[Exception] = None

    # Multiple results from a single call (only used for steps). This will only
    # be longer than 1 for parallel steps. Otherwise, it will be 1 long for
    # sequential steps
    multi: typing.Optional[list[CallResult]] = None

    # Need a sentinel value to differentiate between None and unset
    output: object = types.empty_sentinel

    # Step metadata (e.g. user-specified ID)
    step: typing.Optional[step_lib.StepInfo] = None

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
    attempt: int
    event: server_lib.Event
    events: list[server_lib.Event]
    group: step_lib.Group
    logger: types.Logger
    run_id: str
    step: step_lib.Step


@dataclasses.dataclass
class ContextSync:
    attempt: int
    event: server_lib.Event
    events: list[server_lib.Event]
    group: step_lib.GroupSync
    logger: types.Logger
    run_id: str
    step: step_lib.StepSync


@typing.runtime_checkable
class FunctionHandlerAsync(typing.Protocol):
    def __call__(
        self,
        ctx: Context,
    ) -> typing.Awaitable[types.JSON]: ...


@typing.runtime_checkable
class FunctionHandlerSync(typing.Protocol):
    def __call__(
        self,
        ctx: ContextSync,
    ) -> types.JSON: ...


# Context variable to detect nested steps.
_in_step = contextvars.ContextVar("in_step", default=False)


class ReportedStep:
    _in_step_token: typing.Optional[contextvars.Token[bool]] = None

    def __init__(
        self,
        step_signal: asyncio.Future[ReportedStep],
        step_info: step_lib.StepInfo,
    ) -> None:
        self.error: typing.Optional[errors.StepError] = None
        self.info = step_info
        self.output: object = types.empty_sentinel
        self.skip = False
        self._release_signal = step_signal
        self._done_signal = asyncio.Future[None]()

    async def __aenter__(self) -> ReportedStep:
        if _in_step.get() is True:
            self.info.op = server_lib.Opcode.STEP_ERROR
            raise step_lib.NestedStepInterrupt()
        self._in_step_token = _in_step.set(True)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._in_step_token is None:
            raise errors.UnreachableError("missing in_step token")
        _in_step.reset(self._in_step_token)
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
    _in_step_token: typing.Optional[contextvars.Token[bool]] = None

    def __init__(self, step_info: step_lib.StepInfo) -> None:
        self.error: typing.Optional[errors.StepError] = None
        self.info = step_info
        self.output: object = types.empty_sentinel
        self.skip = False

    def __enter__(self) -> ReportedStepSync:
        if _in_step.get() is True:
            raise step_lib.NestedStepInterrupt()
        self._in_step_token = _in_step.set(True)
        return self

    def __exit__(self, *args: object) -> None:
        if self._in_step_token is None:
            raise errors.UnreachableError("missing in_step token")
        _in_step.reset(self._in_step_token)


class UserError(Exception):
    """
    Wrap an error that occurred in user code.
    """

    def __init__(self, err: Exception) -> None:
        self.err = err
