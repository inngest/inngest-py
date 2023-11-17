import datetime
import typing

from inngest._internal import errors, event_lib, execution, transforms, types

from . import base


class StepSync(base.StepBase):
    def _experimental_parallel(
        self,
        callables: tuple[typing.Callable[[], types.T], ...],
    ) -> tuple[types.T, ...]:
        """
        Run multiple steps in parallel.

        Args:
        ----
            callables: An arbitrary number of step callbacks to run. These are
                callables that contain the step (e.g. `lambda: step.run("my_step", my_step_fn)`.
        """

        self._inside_parallel = True

        outputs = tuple[types.T]()
        responses: list[execution.StepResponse] = []
        for cb in callables:
            try:
                output = cb()
                outputs = (*outputs, output)
            except base.ResponseInterrupt as interrupt:
                responses = [*responses, *interrupt.responses]
            except base.SkipInterrupt:
                pass

        if len(responses) > 0:
            raise base.ResponseInterrupt(responses)

        self._inside_parallel = False
        return outputs

    def run(
        self,
        step_id: str,
        handler: typing.Callable[[], types.SerializableT],
    ) -> types.SerializableT:
        """
        Run logic that should be retried on error and memoized after success.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.
            handler: The logic to run.
        """
        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo_sync(hashed_id)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data  # type: ignore

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == hashed_id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise base.SkipInterrupt()

        if self._inside_parallel and not is_targeting_enabled:
            # Plan this step because we're in parallel mode.
            raise base.ResponseInterrupt(
                execution.StepResponse(
                    display_name=step_id,
                    id=hashed_id,
                    name=step_id,
                    op=execution.Opcode.PLANNED,
                )
            )

        err = self._middleware.before_execution_sync()
        if isinstance(err, Exception):
            raise err

        raise base.ResponseInterrupt(
            execution.StepResponse(
                data=execution.Output(data=handler()),
                display_name=step_id,
                id=hashed_id,
                name=step_id,
                op=execution.Opcode.STEP,
            )
        )

    def send_event(
        self,
        step_id: str,
        events: event_lib.Event | list[event_lib.Event],
    ) -> list[str]:
        """
        Send an event or list of events.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.
            events: An event or list of events to send.
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
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.
            duration: The number of milliseconds to sleep.
        """
        if isinstance(duration, int):
            until = datetime.datetime.now() + datetime.timedelta(
                milliseconds=duration
            )
        else:
            until = datetime.datetime.now() + duration

        return self.sleep_until(step_id, until)

    def sleep_until(
        self,
        step_id: str,
        until: datetime.datetime,
    ) -> None:
        """
        Sleep until a specific time.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.
            until: The time to sleep until.
        """
        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo_sync(hashed_id)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data  # type: ignore

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == hashed_id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise base.SkipInterrupt()

        err = self._middleware.before_execution_sync()
        if isinstance(err, Exception):
            raise err

        raise base.ResponseInterrupt(
            execution.StepResponse(
                display_name=step_id,
                id=hashed_id,
                name=transforms.to_iso_utc(until),
                op=execution.Opcode.SLEEP,
            )
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
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.
            event: Event name.
            if_exp: An expression to filter events.
            timeout: The maximum number of milliseconds to wait for the event.
        """
        hashed_id = self._get_hashed_id(step_id)

        memo = self._get_memo_sync(hashed_id)
        if not isinstance(memo, types.EmptySentinel):
            if memo.data is None:
                # Timeout
                return None

            # Fulfilled by an event
            event_obj = event_lib.Event.from_raw(memo.data)
            if isinstance(event_obj, Exception):
                raise errors.UnknownError("invalid event shape") from event_obj
            return event_obj

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == hashed_id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise base.SkipInterrupt()

        err = self._middleware.before_execution_sync()
        if isinstance(err, Exception):
            raise err

        timeout_str = transforms.to_duration_str(timeout)
        if isinstance(timeout_str, Exception):
            raise timeout_str

        opts = base.WaitForEventOpts(
            if_exp=if_exp,
            timeout=timeout_str,
        ).to_dict()
        if isinstance(opts, Exception):
            raise opts

        raise base.ResponseInterrupt(
            execution.StepResponse(
                display_name=step_id,
                id=hashed_id,
                name=event,
                op=execution.Opcode.WAIT_FOR_EVENT,
                opts=opts,
            )
        )
