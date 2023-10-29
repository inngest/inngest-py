from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import threading
import traceback
import typing

import pydantic

from . import (
    client_lib,
    const,
    errors,
    event_lib,
    execution,
    function_config,
    transforms,
    types,
)


def create_function(
    opts: FunctionOpts,
    trigger: function_config.TriggerCron | function_config.TriggerEvent,
) -> typing.Callable[[_FunctionHandler], Function]:
    def decorator(func: _FunctionHandler) -> Function:
        return Function(opts, trigger, func)

    return decorator


class FunctionOpts(types.BaseModel):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    batch_events: function_config.Batch | None = None
    cancel: list[function_config.Cancel] | None = None
    debounce: function_config.Debounce | None = None
    id: str
    name: str | None = None
    on_failure: _FunctionHandler | None = None
    rate_limit: function_config.RateLimit | None = None
    retries: int | None = None
    throttle: function_config.Throttle | None = None

    def convert_validation_error(
        self,
        err: pydantic.ValidationError,
    ) -> BaseException:
        return errors.InvalidConfig.from_validation_error(err)


class Function:
    _on_failure_fn_id: str | None = None

    def __init__(
        self,
        opts: FunctionOpts,
        trigger: function_config.TriggerCron | function_config.TriggerEvent,
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
        call: execution.Call,
        client: client_lib.Inngest,
        fn_id: str,
    ) -> list[execution.CallResponse] | str | execution.CallError:
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
                    raise errors.MissingFunction("on_failure not defined")

                res = self._opts.on_failure(
                    attempt=call.ctx.attempt,
                    event=call.event,
                    events=call.events,
                    run_id=call.ctx.run_id,
                    step=Step(client, call.steps, _StepIDCounter()),
                )
            else:
                raise errors.MissingFunction("function ID mismatch")

            return json.dumps(res)
        except _Interrupt as out:
            return [
                execution.CallResponse(
                    data=out.data,
                    display_name=out.display_name,
                    id=out.hashed_id,
                    name=out.name,
                    op=out.op,
                    opts=out.opts,
                )
            ]
        except Exception as err:
            is_retriable = isinstance(err, errors.NonRetriableError) is False

            return execution.CallError(
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
            retries = function_config.Retries(attempts=self._opts.retries)
        else:
            retries = None

        main = function_config.FunctionConfig(
            batch_events=self._opts.batch_events,
            cancel=self._opts.cancel,
            debounce=self._opts.debounce,
            id=fn_id,
            name=name,
            rate_limit=self._opts.rate_limit,
            steps={
                const.ROOT_STEP_ID: function_config.Step(
                    id=const.ROOT_STEP_ID,
                    name=const.ROOT_STEP_ID,
                    retries=retries,
                    runtime=function_config.Runtime(
                        type="http",
                        url=f"{app_url}?fnId={fn_id}&stepId={const.ROOT_STEP_ID}",
                    ),
                ),
            },
            throttle=self._opts.throttle,
            triggers=[self._trigger],
        )

        on_failure = None
        if self.on_failure_fn_id is not None:
            on_failure = function_config.FunctionConfig(
                id=self.on_failure_fn_id,
                name=f"{name} (on_failure handler)",
                steps={
                    const.ROOT_STEP_ID: function_config.Step(
                        id=const.ROOT_STEP_ID,
                        name=const.ROOT_STEP_ID,
                        retries=function_config.Retries(attempts=0),
                        runtime=function_config.Runtime(
                            type="http",
                            url=f"{app_url}?fnId={self.on_failure_fn_id}&stepId={const.ROOT_STEP_ID}",
                        ),
                    )
                },
                triggers=[
                    function_config.TriggerEvent(
                        event=const.InternalEvents.FUNCTION_FAILED.value,
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
        op: execution.Opcode,
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
        client: client_lib.Inngest,
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
        return transforms.hash_step_id(step_id)

    def _get_memo(self, hashed_id: str) -> object:
        if hashed_id in self._memos:
            return self._memos[hashed_id]

        return types.EmptySentinel

    def run(
        self,
        step_id: str,
        handler: typing.Callable[[], types.T],
    ) -> types.T:
        """
        Run logic that should be retried on error and memoized after success.
        """

        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo(hashed_id)
        if memo is not types.EmptySentinel:
            return memo  # type: ignore

        output = handler()

        try:
            json.dumps(output)
        except TypeError as err:
            raise errors.UnserializableOutput(str(err)) from None

        raise _Interrupt(
            hashed_id=hashed_id,
            data=output,
            display_name=step_id,
            op=execution.Opcode.STEP,
            name=step_id,
        )

    def send_event(
        self,
        step_id: str,
        events: event_lib.Event | list[event_lib.Event],
    ) -> list[str]:
        """
        Send an event or list of events.
        """

        return self.run(step_id, lambda: self._client.send(events))

    def sleep(
        self,
        step_id: str,
        duration: int | datetime.timedelta,
    ) -> None:
        """
        Sleep for a duration.

        Args:
            duration: The number of milliseconds to sleep.
        """

        if isinstance(duration, int):
            until = datetime.datetime.utcnow() + datetime.timedelta(
                milliseconds=duration
            )
        else:
            until = datetime.datetime.utcnow() + duration

        return self.sleep_until(step_id, until)

    def sleep_until(
        self,
        step_id: str,
        until: datetime.datetime,
    ) -> None:
        """
        Sleep until a specific time.
        """

        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo(hashed_id)
        if memo is not types.EmptySentinel:
            return memo  # type: ignore

        raise _Interrupt(
            hashed_id=hashed_id,
            display_name=step_id,
            name=transforms.to_iso_utc(until),
            op=execution.Opcode.SLEEP,
        )

    def wait_for_event(
        self,
        step_id: str,
        *,
        event: str,
        if_exp: str | None = None,
        timeout: int | datetime.timedelta,
    ) -> event_lib.Event | None:
        """
        Wait for an event to be sent.

        Args:
            event: Event name.
            if_exp: An expression to filter events.
            timeout: The maximum number of milliseconds to wait for the event.
        """

        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo(hashed_id)
        if memo is not types.EmptySentinel:
            if memo is None:
                # Timeout
                return None

            # Fulfilled by an event
            return event_lib.Event.model_validate(memo)

        opts: dict[str, object] = {
            "timeout": transforms.to_duration_str(timeout),
        }
        if if_exp is not None:
            opts["if"] = if_exp

        raise _Interrupt(
            hashed_id=hashed_id,
            display_name=step_id,
            name=event,
            op=execution.Opcode.WAIT_FOR_EVENT,
            opts=opts,
        )


@dataclasses.dataclass
class _Config:
    # The user-defined function
    main: function_config.FunctionConfig

    # The internal on_failure function
    on_failure: function_config.FunctionConfig | None


@typing.runtime_checkable
class _FunctionHandler(typing.Protocol):
    def __call__(
        self,
        *,
        attempt: int,
        event: event_lib.Event,
        events: list[event_lib.Event],
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
