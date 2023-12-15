import datetime
import typing

from inngest._internal import event_lib, execution, transforms, types

from . import base

# Avoid circular import at runtime
if typing.TYPE_CHECKING:
    from inngest._internal.function import Function
else:
    Function = object


class Step(base.StepBase):
    async def invoke(
        self,
        step_id: str,
        *,
        app_id: str | None = None,
        function: Function | str,
        data: types.Serializable | None = None,
        user: types.Serializable | None = None,
        v: str | None = None,
    ) -> object:
        """
        Invoke an Inngest function with data. Returns the result of the returned
        value of the function or `None` if the function does not return a value.

        Functions can be invoked by passing their object or specifying their ID
        string. If a function ID string is passed then it is assumed to be in
        the same app as the current function unless an app ID is specified.

        If a function isn't found or otherwise errors, the step will fail and
        raise a `NonRetriableError`.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.

            app_id: The app ID of the function to invoke. Not necessary if this
                function and the invoked function are in the same app. Ignored
                if `function` is an object.
            function: The function to invoke. Can be a function object or a
                function ID.
            data: Will become `event.data` in the invoked function. Must be JSON
                serializable.
            user: Will become `event.user` in the invoked function. Must be JSON
                serializable.
            v: Will become `event.v` in the invoked function.
        """

        hashed_id = self._get_hashed_id(step_id)

        memo = await self._get_memo(hashed_id)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == hashed_id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise base.SkipInterrupt()

        err = await self._middleware.before_execution()
        if isinstance(err, Exception):
            raise err

        fn_id: str
        if isinstance(function, str):
            if app_id is None:
                app_id = self._client.app_id
            fn_id = f"{app_id}-{function}"
        else:
            fn_id = function.id

        opts = base.InvokeOpts(
            function_id=fn_id,
            payload=base.InvokeOptsPayload(
                data=data,
                user=user,
                v=v,
            ),
        ).to_dict()
        if isinstance(opts, Exception):
            raise opts

        raise base.ResponseInterrupt(
            execution.StepResponse(
                display_name=step_id,
                id=hashed_id,
                name=step_id,
                op=execution.Opcode.INVOKE,
                opts=opts,
            )
        )

    async def parallel(
        self,
        callables: tuple[typing.Callable[[], typing.Awaitable[types.T]], ...],
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
                output = await cb()
                outputs = (*outputs, output)
            except base.ResponseInterrupt as interrupt:
                responses = [*responses, *interrupt.responses]
            except base.SkipInterrupt:
                pass

        if len(responses) > 0:
            raise base.ResponseInterrupt(responses)

        self._inside_parallel = False
        return outputs

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

        memo = await self._get_memo(hashed_id)
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

        err = await self._middleware.before_execution()
        if isinstance(err, Exception):
            raise err

        raise base.ResponseInterrupt(
            execution.StepResponse(
                data=execution.Output(
                    data=await transforms.maybe_await(handler())
                ),
                display_name=step_id,
                id=hashed_id,
                name=step_id,
                op=execution.Opcode.STEP,
            ),
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

        memo = await self._get_memo(hashed_id)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data  # type: ignore

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == hashed_id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise base.SkipInterrupt()

        err = await self._middleware.before_execution()
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

        memo = await self._get_memo(hashed_id)
        if not isinstance(memo, types.EmptySentinel):
            if memo.data is None:
                # Timeout
                return None

            # Fulfilled by an event
            return event_lib.Event.model_validate(memo.data)

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == hashed_id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise base.SkipInterrupt()

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

        raise base.ResponseInterrupt(
            execution.StepResponse(
                id=hashed_id,
                display_name=step_id,
                name=event,
                op=execution.Opcode.WAIT_FOR_EVENT,
                opts=opts,
            )
        )
