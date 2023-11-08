import datetime
import typing

from inngest._internal import event_lib, execution, transforms, types

from . import base


class Step(base.StepBase):
    @typing.overload
    async def run(
        self,
        step_id: str,
        handler: typing.Callable[[], typing.Awaitable[types.SerializableT]],
    ) -> types.SerializableT:
        ...

    @typing.overload
    async def run(
        self,
        step_id: str,
        handler: typing.Callable[[], types.SerializableT],
    ) -> types.SerializableT:
        ...

    async def run(
        self,
        step_id: str,
        handler: typing.Callable[[], typing.Awaitable[types.SerializableT]]
        | typing.Callable[[], types.SerializableT],
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

        memo = await self.get_memo(hashed_id)
        if memo is not types.EmptySentinel:
            return memo  # type: ignore

        err = await self._middleware.before_execution()
        if isinstance(err, Exception):
            raise err

        raise base.Interrupt(
            hashed_id=hashed_id,
            data=await transforms.maybe_await(handler()),
            display_name=step_id,
            op=execution.Opcode.STEP,
            name=step_id,
        )

    async def send_event(
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

        async def fn() -> list[str]:
            return await self._client.send(events)

        return await self.run(step_id, fn)

    async def sleep(
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

        return await self.sleep_until(step_id, until)

    async def sleep_until(
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

        memo = await self.get_memo(hashed_id)
        if memo is not types.EmptySentinel:
            return memo  # type: ignore

        err = await self._middleware.before_execution()
        if isinstance(err, Exception):
            raise err

        raise base.Interrupt(
            hashed_id=hashed_id,
            display_name=step_id,
            name=transforms.to_iso_utc(until),
            op=execution.Opcode.SLEEP,
        )

    async def wait_for_event(
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

        memo = await self.get_memo(hashed_id)
        if memo is not types.EmptySentinel:
            if memo is None:
                # Timeout
                return None

            # Fulfilled by an event
            return event_lib.Event.model_validate(memo)

        err = await self._middleware.before_execution()
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

        raise base.Interrupt(
            hashed_id=hashed_id,
            display_name=step_id,
            name=event,
            op=execution.Opcode.WAIT_FOR_EVENT,
            opts=opts,
        )
