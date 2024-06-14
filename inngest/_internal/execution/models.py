from __future__ import annotations

import asyncio
import dataclasses
import typing

import pydantic

from inngest._internal import errors, event_lib, transforms, types

if typing.TYPE_CHECKING:
    from inngest._internal import step_lib


class Call(types.BaseModel):
    ctx: CallContext
    event: event_lib.Event
    events: typing.Optional[list[event_lib.Event]] = None
    steps: dict[str, object]
    use_api: bool


class CallContext(types.BaseModel):
    attempt: int
    run_id: str
    stack: CallStack


class CallStack(types.BaseModel):
    stack: typing.Optional[list[str]] = None


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
    event: event_lib.Event
    events: list[event_lib.Event]
    logger: types.Logger
    run_id: str


@typing.runtime_checkable
class FunctionHandlerAsync(typing.Protocol):
    def __call__(
        self,
        ctx: Context,
        step: step_lib.Step,
    ) -> typing.Awaitable[types.JSON]:
        ...


@typing.runtime_checkable
class FunctionHandlerSync(typing.Protocol):
    def __call__(
        self,
        ctx: Context,
        step: step_lib.StepSync,
    ) -> types.JSON:
        ...


class Output(types.BaseModel):
    # Fail validation if any extra fields exist, because this will prevent
    # accidentally assuming user data is nested data
    model_config = pydantic.ConfigDict(extra="forbid")

    data: object = None
    error: typing.Optional[MemoizedError] = None


class MemoizedError(types.BaseModel):
    message: str
    name: str
    stack: typing.Optional[str] = None

    @classmethod
    def from_error(cls, err: Exception) -> MemoizedError:
        return cls(
            message=str(err),
            name=type(err).__name__,
            stack=transforms.get_traceback(err),
        )


class ReportedStep:
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
        return self

    async def __aexit__(self, *args: object) -> None:
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


class UserError(Exception):
    """
    Wrap an error that occurred in user code.
    """

    def __init__(self, err: Exception) -> None:
        self.err = err
