from __future__ import annotations

import datetime
import typing

import typing_extensions

from inngest._internal import errors, server_lib, transforms, types
from inngest._internal.client_lib import models as client_models

from . import base

# Avoid circular import at runtime
if typing.TYPE_CHECKING:
    from inngest._internal import (
        client_lib,
        execution_lib,
        function,
        middleware_lib,
    )


class StepSync(base.StepBase):
    def __init__(
        self,
        client: client_lib.Inngest,
        exe: execution_lib.BaseExecutionSync,
        memos: base.StepMemos,
        middleware: middleware_lib.MiddlewareManager,
        step_id_counter: base.StepIDCounter,
        target_hashed_id: typing.Optional[str],
    ) -> None:
        super().__init__(
            client,
            memos,
            middleware,
            step_id_counter,
            target_hashed_id,
        )

        self._execution = exe

    def invoke(
        self,
        step_id: str,
        *,
        function: function.Function,
        data: typing.Optional[types.JSON] = None,
        timeout: typing.Union[int, datetime.timedelta, None] = None,
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
            step_id: Durable step ID. Should usually be unique within a function, but it's OK to reuse as long as your function is deterministic.

            function: The function object to invoke.
            data: Will become `event.data` in the invoked function. Must be JSON serializable.
            timeout: The maximum number of milliseconds to wait for the function to complete.
            user: Will become `event.user` in the invoked function. Must be JSON serializable.
            v: Will become `event.v` in the invoked function.
        """

        return self.invoke_by_id(
            step_id,
            app_id=self._client.app_id,
            function_id=function._opts.local_id,
            data=data,
            timeout=timeout,
            user=user,
            v=v,
        )

    def invoke_by_id(
        self,
        step_id: str,
        *,
        app_id: typing.Optional[str] = None,
        function_id: str,
        data: typing.Optional[types.JSON] = None,
        timeout: typing.Union[int, datetime.timedelta, None] = None,
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
            step_id: Durable step ID. Should usually be unique within a function, but it's OK to reuse as long as your function is deterministic.

            app_id: The app ID of the function to invoke. Not necessary if this function and the invoked function are in the same app.
            function_id: The ID of the function to invoke.
            data: Will become `event.data` in the invoked function. Must be JSON serializable.
            timeout: The maximum number of milliseconds to wait for the function to complete.
            user: Will become `event.user` in the invoked function. Must be JSON serializable.
            v: Will become `event.v` in the invoked function.
        """

        parsed_step_id = self._parse_step_id(step_id)

        memo = self._get_memo_sync(parsed_step_id.hashed)
        if not isinstance(memo, types.EmptySentinel):
            return memo.data

        self._handle_skip(parsed_step_id)

        err = self._middleware.before_execution_sync()
        if isinstance(err, Exception):
            raise err

        timeout_str = transforms.to_maybe_duration_str(timeout)
        if isinstance(timeout_str, Exception):
            raise timeout_str

        opts = base.InvokeOpts(
            function_id=f"{app_id}-{function_id}",
            payload=base.InvokeOptsPayload(
                data=data,
                user=user,
                v=v,
            ),
            timeout=timeout_str,
        ).to_dict()
        if isinstance(opts, Exception):
            raise opts

        step_info = base.StepInfo(
            display_name=parsed_step_id.user_facing,
            id=parsed_step_id.hashed,
            name=parsed_step_id.user_facing,
            op=server_lib.Opcode.INVOKE,
            opts=opts,
        )

        with self._execution.report_step(
            step_info,
            self._inside_parallel,
        ) as step:
            if step.skip:
                raise base.SkipInterrupt(parsed_step_id.user_facing)
            if step.error is not None:
                raise step.error
            elif not isinstance(step.output, types.EmptySentinel):
                return step.output

        raise Exception("unreachable")

    def parallel(
        self,
        callables: tuple[typing.Callable[[], types.T], ...],
    ) -> tuple[types.T, ...]:
        """
        Run multiple steps in parallel.

        Args:
        ----
            callables: An arbitrary number of step callbacks to run. These are callables that contain the step (e.g. `lambda: step.run("my_step", my_step_fn)`.
        """

        self._inside_parallel = True

        outputs = tuple[types.T]()
        responses: list[base.StepResponse] = []
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
        handler: typing.Callable[
            [typing_extensions.Unpack[types.TTuple]],
            types.JSONT,
        ],
        *handler_args: typing_extensions.Unpack[types.TTuple],
    ) -> types.JSONT:
        """
        Run logic that should be retried on error and memoized after success.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a function, but it's OK to reuse as long as your function is deterministic.
            handler: The logic to run.
            *handler_args: Arguments to pass to the handler.
        """

        parsed_step_id = self._parse_step_id(step_id)

        step_info = base.StepInfo(
            display_name=parsed_step_id.user_facing,
            id=parsed_step_id.hashed,
            name=parsed_step_id.user_facing,
            op=server_lib.Opcode.STEP_RUN,
        )

        with self._execution.report_step(
            step_info,
            self._inside_parallel,
        ) as step:
            if step.skip:
                raise base.SkipInterrupt(parsed_step_id.user_facing)
            if step.error is not None:
                raise step.error
            elif not isinstance(step.output, types.EmptySentinel):
                return step.output  # type: ignore

            try:
                output = handler(*handler_args)

                raise base.ResponseInterrupt(
                    base.StepResponse(
                        output=output,
                        step=step_info,
                    )
                )
            except (errors.NonRetriableError, errors.RetryAfterError) as err:
                # Bubble up these error types to the function level
                raise err
            except Exception as err:
                transforms.remove_first_traceback_frame(err)

                step_info.op = server_lib.Opcode.STEP_ERROR

                raise base.ResponseInterrupt(
                    base.StepResponse(
                        original_error=err,
                        step=step_info,
                    )
                )

    def send_event(
        self,
        step_id: str,
        events: typing.Union[server_lib.Event, list[server_lib.Event]],
    ) -> list[str]:
        """
        Send an event or list of events.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a function, but it's OK to reuse as long as your function is deterministic.
            events: An event or list of events to send.
        """

        def fn() -> list[str]:
            if isinstance(events, list):
                _events = events
            else:
                _events = [events]

            middleware_err = self._middleware.before_send_events_sync(_events)
            if isinstance(middleware_err, Exception):
                raise middleware_err

            try:
                result = client_models.SendEventsResult(
                    ids=self._client.send_sync(
                        events,
                        # Skip middleware since we're already running it above. Without
                        # this, we'll double-call middleware hooks
                        skip_middleware=True,
                    )
                )
            except errors.SendEventsError as err:
                result = client_models.SendEventsResult(
                    error=str(err),
                    ids=err.ids,
                )
                raise err
            finally:
                middleware_err = self._middleware.after_send_events_sync(result)
                if isinstance(middleware_err, Exception):
                    raise middleware_err

            return result.ids

        return self.run(step_id, fn)

    def sleep(
        self,
        step_id: str,
        duration: typing.Union[int, datetime.timedelta],
    ) -> None:
        """
        Sleep for a duration.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a function, but it's OK to reuse as long as your function is deterministic.
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
            step_id: Durable step ID. Should usually be unique within a function, but it's OK to reuse as long as your function is deterministic.
            until: The time to sleep until.
        """

        parsed_step_id = self._parse_step_id(step_id)

        step_info = base.StepInfo(
            display_name=parsed_step_id.user_facing,
            id=parsed_step_id.hashed,
            name=transforms.to_iso_utc(until),
            op=server_lib.Opcode.SLEEP,
        )

        with self._execution.report_step(
            step_info,
            self._inside_parallel,
        ) as step:
            if step.skip:
                raise base.SkipInterrupt(parsed_step_id.user_facing)
            if step.error is not None:
                raise step.error
            elif not isinstance(step.output, types.EmptySentinel):
                return step.output  # type: ignore

        raise Exception("unreachable")

    def wait_for_event(
        self,
        step_id: str,
        *,
        event: str,
        if_exp: typing.Optional[str] = None,
        timeout: typing.Union[int, datetime.timedelta],
    ) -> typing.Optional[server_lib.Event]:
        """
        Wait for an event to be sent.

        Args:
        ----
            step_id: Durable step ID. Should usually be unique within a function, but it's OK to reuse as long as your function is deterministic.
            event: Event name.
            if_exp: An expression to filter events.
            timeout: The maximum number of milliseconds to wait for the event.
        """

        parsed_step_id = self._parse_step_id(step_id)

        memo = self._get_memo_sync(parsed_step_id.hashed)
        if not isinstance(memo, types.EmptySentinel):
            if memo.data is None:
                # Timeout
                return None

            # Fulfilled by an event
            event_obj = server_lib.Event.from_raw(memo.data)
            if isinstance(event_obj, Exception):
                raise errors.UnknownError("invalid event shape") from event_obj
            return event_obj

        self._handle_skip(parsed_step_id)

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

        step_info = base.StepInfo(
            id=parsed_step_id.hashed,
            display_name=parsed_step_id.user_facing,
            name=event,
            op=server_lib.Opcode.WAIT_FOR_EVENT,
            opts=opts,
        )

        with self._execution.report_step(
            step_info,
            self._inside_parallel,
        ) as step:
            if step.skip:
                raise base.SkipInterrupt(parsed_step_id.user_facing)
            if step.error is not None:
                raise step.error
            elif not isinstance(step.output, types.EmptySentinel):
                if step.output is None:
                    # Timeout
                    return None

                # Fulfilled by an event
                return server_lib.Event.model_validate(step.output)

        raise Exception("unreachable")
