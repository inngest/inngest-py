from __future__ import annotations

import json
import threading
import traceback
from datetime import datetime
from typing import Callable, Protocol, runtime_checkable

from pydantic import ValidationError

from .client import Inngest
from .errors import InvalidConfig, NonRetriableError, UnserializableOutput
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
    retries: int | None = None
    throttle: ThrottleConfig | None = None

    def convert_validation_error(
        self,
        err: ValidationError,
    ) -> BaseException:
        return InvalidConfig.from_validation_error(err)


class Function:
    def __init__(
        self,
        opts: FunctionOpts,
        trigger: TriggerCron | TriggerEvent,
        handler: _FunctionHandler,
    ) -> None:
        self._handler = handler
        self._opts = opts
        self._trigger = trigger

    def call(
        self,
        call: Call,
        client: Inngest,
    ) -> list[CallResponse] | str | CallError:
        try:
            res = self._handler(
                attempt=call.ctx.attempt,
                event=call.event,
                events=call.events,
                run_id=call.ctx.run_id,
                step=_Step(client, call.steps, _StepIDCounter()),
            )
            return json.dumps(res)
        except EarlyReturn as out:
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

    def get_config(self, app_url: str) -> FunctionConfig:
        fn_id = self._opts.id

        name = fn_id
        if self._opts.name is not None:
            name = self._opts.name

        if self._opts.retries is not None:
            retries = RetriesConfig(attempts=self._opts.retries)
        else:
            retries = None

        return FunctionConfig(
            batch_events=self._opts.batch_events,
            cancel=self._opts.cancel,
            id=fn_id,
            name=name,
            steps={
                "step": StepConfig(
                    id="step",
                    name="step",
                    retries=retries,
                    runtime=Runtime(
                        type="http",
                        url=f"{app_url}?fnId={fn_id}&stepId=step",
                    ),
                ),
            },
            throttle=self._opts.throttle,
            triggers=[self._trigger],
        )

    def get_id(self) -> str:
        return self._opts.id


# Extend BaseException to avoid being caught by the user's code. Users can still
# catch it if they do a "bare except", but that's a known antipattern in the
# Python world.
class EarlyReturn(BaseException):
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


class _Step:
    def __init__(
        self,
        client: Inngest,
        memos: dict[str, object],
        step_id_counter: _StepIDCounter,
    ) -> None:
        self._client = client
        self._memos = memos
        self._step_id_counter = step_id_counter

    def _get_memo(self, hashed_id: str) -> object:
        if hashed_id in self._memos:
            return self._memos[hashed_id]

        return EmptySentinel

    def run(
        self,
        id: str,  # pylint: disable=redefined-builtin
        handler: Callable[[], T],
    ) -> T:
        id_count = self._step_id_counter.increment(id)
        if id_count > 1:
            id = f"{id}:{id_count - 1}"
        hashed_id = hash_step_id(id)

        memo = self._get_memo(hashed_id)
        if memo is not EmptySentinel:
            return memo  # type: ignore

        output = handler()

        try:
            json.dumps(output)
        except TypeError as err:
            raise UnserializableOutput(str(err)) from None

        raise EarlyReturn(
            hashed_id=hashed_id,
            data=output,
            display_name=id,
            op=Opcode.STEP,
            name=id,
        )

    def send_event(
        self,
        id: str,  # pylint: disable=redefined-builtin
        events: Event | list[Event],
    ) -> list[str]:
        return self.run(id, lambda: self._client.send(events))

    def sleep_until(
        self,
        id: str,  # pylint: disable=redefined-builtin
        time: datetime,
    ) -> None:
        id_count = self._step_id_counter.increment(id)
        if id_count > 1:
            id = f"{id}:{id_count - 1}"
        hashed_id = hash_step_id(id)

        memo = self._get_memo(hashed_id)
        if memo is not EmptySentinel:
            return memo  # type: ignore

        raise EarlyReturn(
            hashed_id=hashed_id,
            display_name=id,
            name=to_iso_utc(time),
            op=Opcode.SLEEP,
        )

    def wait_for_event(
        self,
        id: str,  # pylint: disable=redefined-builtin
        *,
        event: str,
        if_exp: str | None = None,
        timeout: int,
    ) -> Event | None:
        """
        Args:
            event: Event name.
            if_exp: An expression to filter events.
            timeout: The maximum number of milliseconds to wait for the event.
        """

        id_count = self._step_id_counter.increment(id)
        if id_count > 1:
            id = f"{id}:{id_count - 1}"
        hashed_id = hash_step_id(id)

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

        raise EarlyReturn(
            hashed_id=hashed_id,
            display_name=id,
            name=event,
            op=Opcode.WAIT_FOR_EVENT,
            opts=opts,
        )


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


@runtime_checkable
class Step(Protocol):
    def run(
        self,
        id: str,  # pylint: disable=redefined-builtin
        handler: Callable[[], T],
    ) -> T:
        ...

    def send_event(
        self,
        id: str,  # pylint: disable=redefined-builtin
        events: Event | list[Event],
    ) -> list[str]:
        ...

    def sleep_until(
        self,
        id: str,  # pylint: disable=redefined-builtin
        time: datetime,
    ) -> None:
        ...

    def wait_for_event(
        self,
        id: str,  # pylint: disable=redefined-builtin
        *,
        event: str,
        if_exp: str | None = None,
        timeout: int,
    ) -> Event | None:
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
