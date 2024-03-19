import datetime
import typing

from inngest._internal import errors, event_lib, execution, transforms, types

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
        function: Function,
        data: typing.Optional[types.JSON] = None,
        user: typing.Optional[types.JSON] = None,
        v: typing.Optional[str] = None,
    ) -> object:
        """
        Invoke an Inngest function with data. Returns the result of the returned
        value of the function or `None` if the function does not return a value.

        If a function isn't found or otherwise errors, the step will fail and
        raise a `NonRetriableError`.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.

            function: The function object to invoke.
            data: Will become `event.data` in the invoked function. Must be JSON
                serializable.
            user: Will become `event.user` in the invoked function. Must be JSON
                serializable.
            v: Will become `event.v` in the invoked function.
        """

        return await self.invoke_by_id(
            step_id,
            app_id=self._client.app_id,
            function_id=function._opts.local_id,
            data=data,
            user=user,
            v=v,
        )

    async def invoke_by_id(
        self,
        step_id: str,
        *,
        app_id: typing.Optional[str] = None,
        function_id: str,
        data: typing.Optional[types.JSON] = None,
        user: typing.Optional[types.JSON] = None,
        v: typing.Optional[str] = None,
    ) -> object:
        """
        Invoke an Inngest function with data. Returns the result of the returned
        value of the function or `None` if the function does not return a value.

        If app ID is not specified, the invoked function must be in the same
        app.

        If a function isn't found or otherwise errors, the step will fail and
        raise a `NonRetriableError`.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.

            app_id: The app ID of the function to invoke. Not necessary if this
                function and the invoked function are in the same app.
            function_id: The ID of the function to invoke.
            data: Will become `event.data` in the invoked function. Must be JSON
                serializable.
            user: Will become `event.user` in the invoked function. Must be JSON
                serializable.
            v: Will become `event.v` in the invoked function.
        """

        parsed_step_id = self._parse_step_id(step_id)

        memo = await self._get_memo(parsed_step_id.hashed)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data

        self._handle_skip(parsed_step_id)

        err = await self._middleware.before_execution()
        if isinstance(err, Exception):
            raise err

        opts = base.InvokeOpts(
            function_id=f"{app_id}-{function_id}",
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
                display_name=parsed_step_id.user_facing,
                id=parsed_step_id.hashed,
                name=parsed_step_id.user_facing,
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
        handler: typing.Callable[[], typing.Awaitable[types.JSONT]],
    ) -> types.JSONT:
        ...

    @typing.overload
    async def run(
        self,
        step_id: str,
        handler: typing.Callable[[], types.JSONT],
    ) -> types.JSONT:
        ...

    async def run(
        self,
        step_id: str,
        handler: typing.Union[
            typing.Callable[[], typing.Awaitable[types.JSONT]],
            typing.Callable[[], types.JSONT],
        ],
    ) -> types.JSONT:
        """
        Run logic that should be retried on error and memoized after success.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a
                function, but it's OK to reuse as long as your function is
                deterministic.
            handler: The logic to run.
        """

        parsed_step_id = self._parse_step_id(step_id)

        memo = await self._get_memo(parsed_step_id.hashed)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data  # type: ignore

        self._handle_skip(parsed_step_id)

        is_targeting_enabled = self._target_hashed_id is not None
        if self._inside_parallel and not is_targeting_enabled:
            # Plan this step because we're in parallel mode.
            raise base.ResponseInterrupt(
                execution.StepResponse(
                    display_name=parsed_step_id.user_facing,
                    id=parsed_step_id.hashed,
                    name=parsed_step_id.user_facing,
                    op=execution.Opcode.PLANNED,
                )
            )

        err = await self._middleware.before_execution()
        if isinstance(err, Exception):
            raise err

        try:
            output = await transforms.maybe_await(handler())

            raise base.ResponseInterrupt(
                execution.StepResponse(
                    data=execution.Output(data=output),
                    display_name=parsed_step_id.user_facing,
                    id=parsed_step_id.hashed,
                    name=parsed_step_id.user_facing,
                    op=execution.Opcode.STEP_RUN,
                )
            )
        except errors.NonRetriableError as err:
            # NonRetriableErrors should bubble up to the function level
            raise err
        except Exception as err:
            transforms.remove_first_traceback_frame(err)

            error_dict = execution.MemoizedError.from_error(err).to_dict()
            if isinstance(error_dict, Exception):
                raise error_dict

            raise base.ResponseInterrupt(
                execution.StepResponse(
                    data=execution.Output(error=error_dict),
                    display_name=parsed_step_id.user_facing,
                    id=parsed_step_id.hashed,
                    op=execution.Opcode.STEP_ERROR,
                )
            )

    async def send_event(
        self,
        step_id: str,
        events: typing.Union[event_lib.Event, list[event_lib.Event]],
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
        duration: typing.Union[int, datetime.timedelta],
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

        parsed_step_id = self._parse_step_id(step_id)

        memo = await self._get_memo(parsed_step_id.hashed)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data  # type: ignore

        self._handle_skip(parsed_step_id)

        err = await self._middleware.before_execution()
        if isinstance(err, Exception):
            raise err

        raise base.ResponseInterrupt(
            execution.StepResponse(
                display_name=parsed_step_id.user_facing,
                id=parsed_step_id.hashed,
                name=transforms.to_iso_utc(until),
                op=execution.Opcode.SLEEP,
            )
        )

    async def wait_for_event(
        self,
        step_id: str,
        *,
        event: str,
        if_exp: typing.Optional[str] = None,
        timeout: typing.Union[int, datetime.timedelta],
    ) -> typing.Optional[event_lib.Event]:
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

        parsed_step_id = self._parse_step_id(step_id)

        memo = await self._get_memo(parsed_step_id.hashed)
        if not isinstance(memo, types.EmptySentinel):
            if memo.data is None:
                # Timeout
                return None

            # Fulfilled by an event
            return event_lib.Event.model_validate(memo.data)

        self._handle_skip(parsed_step_id)

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
                id=parsed_step_id.hashed,
                display_name=parsed_step_id.user_facing,
                name=event,
                op=execution.Opcode.WAIT_FOR_EVENT,
                opts=opts,
            )
        )
