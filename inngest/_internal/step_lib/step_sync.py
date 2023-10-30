import datetime
import json
import typing

from inngest._internal import (
    client_lib,
    errors,
    event_lib,
    execution,
    transforms,
    types,
)

from . import base


class StepSync(base.StepBase):
    def __init__(
        self,
        client: client_lib.Inngest,
        memos: dict[str, object],
        step_id_counter: base.StepIDCounter,
    ) -> None:
        self._client = client
        self._memos = memos
        self._step_id_counter = step_id_counter

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

        raise base.Interrupt(
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

        def fn() -> list[str]:
            return self._client.send_sync(events)

        return self.run(step_id, fn)

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

        raise base.Interrupt(
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

        raise base.Interrupt(
            hashed_id=hashed_id,
            display_name=step_id,
            name=event,
            op=execution.Opcode.WAIT_FOR_EVENT,
            opts=opts,
        )
