from __future__ import annotations

import hashlib
import json
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol, runtime_checkable

from pydantic import ValidationError

from .client import Inngest
from .const import ROOT_STEP_ID, InternalEvents
from .errors import (
    InvalidConfig,
    MissingFunction,
    NonRetriableError,
    UnserializableOutput,
)
from .event import Event
from .execution import Call, CallError, CallResponse, Opcode
from .function_config import (
    BatchConfig,
    CancelConfig,
    FunctionConfig,
    RetriesConfig,
    Runtime,
    StepConfig,
    ThrottleConfig,
    TriggerCron,
    TriggerEvent,
)
from .transforms import hash_step_id, to_duration_str, to_iso_utc
from .types import BaseModel, EmptySentinel, T


def create_function(
    opts: FunctionOpts,
    trigger: TriggerCron | TriggerEvent,
) -> Callable[[_FunctionHandler], Function]:
    def decorator(func: _FunctionHandler) -> Function:
        return Function(opts, trigger, func)

    return decorator


class FunctionOpts(BaseModel):
    batch_events: BatchConfig | None = None
    cancel: CancelConfig | None = None
    id: str
    name: str | None = None
    on_failure: _FunctionHandler | None = None
    retries: int | None = None
    throttle: ThrottleConfig | None = None

    class Config:
        arbitrary_types_allowed = True

    def convert_validation_error(
        self,
        err: ValidationError,
    ) -> BaseException:
        return InvalidConfig.from_validation_error(err)


class Function:
    _on_failure_fn_id: str | None = None

    def __init__(
        self,
        opts: FunctionOpts,
        trigger: TriggerCron | TriggerEvent,
        handler: _FunctionHandler,
    ) -> None:
        self._handler = handler
        self._opts = opts
        self._trigger = trigger

        if opts.on_failure is not None:
            # Create a random suffix to avoid collisions with the main
            # function's ID.
            suffix = hashlib.sha1(opts.id.encode("utf-8")).hexdigest()[:8]

            self._on_failure_fn_id = f"{opts.id}-{suffix}"

    @property
    def id(self) -> str:
        return self._opts.id

    @property
    def on_failure_fn_id(self) -> str | None:
        return self._on_failure_fn_id

    def call(
        self,
        call: Call,
        client: Inngest,
        fn_id: str,
    ) -> list[CallResponse] | str | CallError:
        try:
            if self.id == fn_id:
                res = self._handler(
                    attempt=call.ctx.attempt,
                    event=call.event,
                    events=call.events,
                    run_id=call.ctx.run_id,
                    step=Step(client, call.steps, _StepIDCounter()),
                )
            elif self.on_failure_fn_id == fn_id:
                if self._opts.on_failure is None:
                    raise MissingFunction("on_failure not defined")

                res = self._opts.on_failure(
                    attempt=call.ctx.attempt,
                    event=call.event,
                    events=call.events,
                    run_id=call.ctx.run_id,
                    step=Step(client, call.steps, _StepIDCounter()),
                )
            else:
                raise MissingFunction("function ID mismatch")

            return json.dumps(res)
        except _Interrupt as out:
            return [
                CallResponse(
                    data=out.data,
                    display_name=out.display_name,
                    id=out.hashed_id,
                    name=out.name,
                    op=out.op,
                    opts=out.opts,
                )
            ]
        except Exception as err:
            is_retriable = isinstance(err, NonRetriableError) is False

            return CallError(
                is_retriable=is_retriable,
                message=str(err),
                name=type(err).__name__,
                stack=traceback.format_exc(),
            )

    def get_config(self, app_url: str) -> _Config:
        fn_id = self._opts.id

        name = fn_id
        if self._opts.name is not None:
            name = self._opts.name

        if self._opts.retries is not None:
            retries = RetriesConfig(attempts=self._opts.retries)
        else:
            retries = None

        main = FunctionConfig(
            batch_events=self._opts.batch_events,
            cancel=self._opts.cancel,
            id=fn_id,
            name=name,
            steps={
                ROOT_STEP_ID: StepConfig(
                    id=ROOT_STEP_ID,
                    name=ROOT_STEP_ID,
                    retries=retries,
                    runtime=Runtime(
                        type="http",
                        url=f"{app_url}?fnId={fn_id}&stepId={ROOT_STEP_ID}",
                    ),
                ),
            },
            throttle=self._opts.throttle,
            triggers=[self._trigger],
        )

        on_failure = None
        if self.on_failure_fn_id is not None:
            on_failure = FunctionConfig(
                id=self.on_failure_fn_id,
                name=f"{name} (on_failure handler)",
                steps={
                    ROOT_STEP_ID: StepConfig(
                        id=ROOT_STEP_ID,
                        name=ROOT_STEP_ID,
                        retries=RetriesConfig(attempts=0),
                        runtime=Runtime(
                            type="http",
                            url=f"{app_url}?fnId={self.on_failure_fn_id}&stepId={ROOT_STEP_ID}",
                        ),
                    )
                },
                triggers=[
                    TriggerEvent(
                        event=InternalEvents.FUNCTION_FAILED.value,
                        expression=f"event.data.function_id == '{self.id}'",
                    )
                ],
            )

        return _Config(main=main, on_failure=on_failure)

    def get_id(self) -> str:
        return self._opts.id


# Extend BaseException to avoid being caught by the user's code. Users can still
# catch it if they do a "bare except", but that's a known antipattern in the
# Python world.
class _Interrupt(BaseException):
    def __init__(
        self,
        *,
        data: object = None,
        display_name: str,
        hashed_id: str,
        name: str,
        op: Opcode,
        opts: dict[str, object] | None = None,
    ) -> None:
        self.data = data
        self.display_name = display_name
        self.hashed_id = hashed_id
        self.name = name
        self.op = op
        self.opts = opts


class Step:
    def __init__(
        self,
        client: Inngest,
        memos: dict[str, object],
        step_id_counter: _StepIDCounter,
    ) -> None:
        self._client = client
        self._memos = memos
        self._step_id_counter = step_id_counter

    def _get_hashed_id(self, step_id: str) -> str:
        id_count = self._step_id_counter.increment(step_id)
        if id_count > 1:
            step_id = f"{step_id}:{id_count - 1}"
        return hash_step_id(step_id)

    def _get_memo(self, hashed_id: str) -> object:
        if hashed_id in self._memos:
            return self._memos[hashed_id]

        return EmptySentinel

    def run(
        self,
        step_id: str,
        handler: Callable[[], T],
    ) -> T:
        """
        Run logic that should be retried on error and memoized after success.
        """

        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo(hashed_id)
        if memo is not EmptySentinel:
            return memo  # type: ignore

        output = handler()

        try:
            json.dumps(output)
        except TypeError as err:
            raise UnserializableOutput(str(err)) from None

        raise _Interrupt(
            hashed_id=hashed_id,
            data=output,
            display_name=step_id,
            op=Opcode.STEP,
            name=step_id,
        )

    def send_event(
        self,
        step_id: str,
        events: Event | list[Event],
    ) -> list[str]:
        """
        Send an event or list of events.
        """

        return self.run(step_id, lambda: self._client.send(events))

    def sleep(
        self,
        step_id: str,
        duration: int | timedelta,
    ) -> None:
        """
        Sleep for a duration.

        Args:
            duration: The number of milliseconds to sleep.
        """

        if isinstance(duration, int):
            until = datetime.utcnow() + timedelta(milliseconds=duration)
        else:
            until = datetime.utcnow() + duration

        return self.sleep_until(step_id, until)

    def sleep_until(
        self,
        step_id: str,
        until: datetime,
    ) -> None:
        """
        Sleep until a specific time.
        """

        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo(hashed_id)
        if memo is not EmptySentinel:
            return memo  # type: ignore

        raise _Interrupt(
            hashed_id=hashed_id,
            display_name=step_id,
            name=to_iso_utc(until),
            op=Opcode.SLEEP,
        )

    def wait_for_event(
        self,
        step_id: str,
        *,
        event: str,
        if_exp: str | None = None,
        timeout: int | timedelta,
    ) -> Event | None:
        """
        Wait for an event to be sent.

        Args:
            event: Event name.
            if_exp: An expression to filter events.
            timeout: The maximum number of milliseconds to wait for the event.
        """

        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo(hashed_id)
        if memo is not EmptySentinel:
            if memo is None:
                # Timeout
                return None

            # Fulfilled by an event
            return Event.model_validate(memo)

        opts: dict[str, object] = {
            "timeout": to_duration_str(timeout),
        }
        if if_exp is not None:
            opts["if"] = if_exp

        raise _Interrupt(
            hashed_id=hashed_id,
            display_name=step_id,
            name=event,
            op=Opcode.WAIT_FOR_EVENT,
            opts=opts,
        )


@dataclass
class _Config:
    # The user-defined function
    main: FunctionConfig

    # The internal on_failure function
    on_failure: FunctionConfig | None


@runtime_checkable
class _FunctionHandler(Protocol):
    def __call__(
        self,
        *,
        attempt: int,
        event: Event,
        events: list[Event],
        run_id: str,
        step: Step,
    ) -> object:
        ...


class _StepIDCounter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._mutex = threading.Lock()

    def increment(self, hashed_id: str) -> int:
        with self._mutex:
            if hashed_id not in self._counts:
                self._counts[hashed_id] = 0

            self._counts[hashed_id] += 1
            return self._counts[hashed_id]
