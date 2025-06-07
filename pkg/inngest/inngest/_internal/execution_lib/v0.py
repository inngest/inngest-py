from __future__ import annotations

import asyncio
import typing

from inngest._internal import errors, server_lib, step_lib, transforms, types
from inngest._internal.execution_lib import BaseExecution, BaseExecutionSync

from .models import (
    CallResult,
    Context,
    ContextSync,
    FunctionHandlerAsync,
    FunctionHandlerSync,
    ReportedStep,
    ReportedStepSync,
    UserError,
)

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, function, middleware_lib


class ExecutionV0(BaseExecution):
    version = "0"

    def __init__(
        self,
        memos: step_lib.StepMemos,
        middleware: middleware_lib.MiddlewareManager,
        request: server_lib.ServerRequest,
        target_hashed_id: typing.Optional[str],
    ) -> None:
        self._memos = memos
        self._middleware = middleware
        self._request = request
        self._target_hashed_id = target_hashed_id

    def _handle_skip(
        self,
        step_info: step_lib.StepInfo,
    ) -> None:
        """
        Handle a skip interrupt. Step targeting is enabled and this step is not
        the target then skip the step.
        """

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == step_info.id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise step_lib.SkipInterrupt(step_info.display_name)

    async def report_step(
        self,
        step_info: step_lib.StepInfo,
    ) -> ReportedStep:
        step_signal = asyncio.Future[ReportedStep]()

        step = ReportedStep(step_signal, step_info)
        await step.release()

        memo = self._memos.pop(step.info.id)

        # If there are no more memos then all future code is new.
        if self._memos.size == 0:
            await self._middleware.before_execution()

        if not isinstance(memo, types.EmptySentinel):
            if memo.error is not None:
                step.error = errors.StepError(
                    message=memo.error.message,
                    name=memo.error.name,
                    stack=memo.error.stack,
                )
            elif not isinstance(memo.data, types.EmptySentinel):
                step.output = memo.data

            return step

        self._handle_skip(step_info)

        is_targeting_enabled = self._target_hashed_id is not None
        if step_lib.in_parallel.get() and not is_targeting_enabled:
            if step_info.op == server_lib.Opcode.STEP_RUN:
                step_info.op = server_lib.Opcode.PLANNED

            # Plan this step because we're in parallel mode.
            raise step_lib.ResponseInterrupt(
                step_lib.StepResponse(step=step_info)
            )

        if (
            step_info.op == server_lib.Opcode.STEP_RUN
            and self._request.ctx.disable_immediate_execution is True
            and not is_targeting_enabled
        ):
            # We should only get here when encountering a new, single step.run
            # after parallel steps

            step_info.op = server_lib.Opcode.PLANNED

            raise step_lib.ResponseInterrupt(
                step_lib.StepResponse(step=step_info)
            )

        if step_info.op == server_lib.Opcode.STEP_RUN:
            return step

        raise step_lib.ResponseInterrupt(step_lib.StepResponse(step=step_info))

    async def run(
        self,
        client: client_lib.Inngest,
        ctx: Context,
        handler: FunctionHandlerAsync[types.T],
        fn: function.Function[types.T],
        output_type: object = types.EmptySentinel,
    ) -> CallResult:
        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        middleware_err = await self._middleware.transform_input(
            ctx,
            fn,
            self._memos,
        )
        if isinstance(middleware_err, Exception):
            return CallResult(middleware_err)

        # No memoized data means we're calling the function for the first time.
        if self._memos.size == 0:
            err = await self._middleware.before_execution()
            if isinstance(err, Exception):
                return CallResult(err)

        try:
            try:
                output: object = await handler(ctx)

                # Even though output_type isn't used, we still check for it to
                # ensure users are adding explicit types on functions that
                # return non-JSON-serializable data (e.g. Pydantic objects). If
                # we didn't do this, then `step.invoke` would not return the
                # correct type at runtime.
                if (
                    client._serializer is not None
                    and output_type is not types.EmptySentinel
                ):
                    output = client._serializer.serialize(output)
            except Exception as user_err:
                transforms.remove_first_traceback_frame(user_err)
                raise UserError(user_err)

            err = await self._middleware.after_execution()
            if isinstance(err, Exception):
                return CallResult(err)

            return CallResult(output=output)
        except step_lib.ResponseInterrupt as interrupt:
            err = await self._middleware.after_execution()
            if isinstance(err, Exception):
                return CallResult(err)

            return CallResult.from_responses(interrupt.responses)
        except UserError as err:
            return CallResult(err.err)
        except step_lib.SkipInterrupt as err:
            # This should only happen in a non-deterministic scenario, where
            # step targeting is enabled and an unexpected step is encountered.
            # We don't currently have a way to recover from this scenario.

            return CallResult(
                errors.StepUnexpectedError(
                    f'found step "{err.step_id}" when targeting a different step'
                )
            )
        except Exception as err:
            return CallResult(err)


class ExecutionV0Sync(BaseExecutionSync):
    version = "0"

    def __init__(
        self,
        memos: step_lib.StepMemos,
        middleware: middleware_lib.MiddlewareManager,
        request: server_lib.ServerRequest,
        target_hashed_id: typing.Optional[str],
    ) -> None:
        self._memos = memos
        self._middleware = middleware
        self._request = request
        self._target_hashed_id = target_hashed_id

    def _handle_skip(
        self,
        step_info: step_lib.StepInfo,
    ) -> None:
        """
        Handle a skip interrupt. Step targeting is enabled and this step is not
        the target then skip the step.
        """

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == step_info.id
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise step_lib.SkipInterrupt(step_info.display_name)

    def report_step(
        self,
        step_info: step_lib.StepInfo,
    ) -> ReportedStepSync:
        step = ReportedStepSync(step_info)

        memo = self._memos.pop(step.info.id)

        # If there are no more memos then all future code is new.
        if self._memos.size == 0:
            self._middleware.before_execution_sync()

        if not isinstance(memo, types.EmptySentinel):
            if memo.error is not None:
                step.error = errors.StepError(
                    message=memo.error.message,
                    name=memo.error.name,
                    stack=memo.error.stack,
                )
            elif not isinstance(memo.data, types.EmptySentinel):
                step.output = memo.data

            return step

        self._handle_skip(step_info)

        is_targeting_enabled = self._target_hashed_id is not None
        if step_lib.in_parallel.get() and not is_targeting_enabled:
            if step_info.op == server_lib.Opcode.STEP_RUN:
                step_info.op = server_lib.Opcode.PLANNED

            # Plan this step because we're in parallel mode.
            raise step_lib.ResponseInterrupt(
                step_lib.StepResponse(step=step_info)
            )

        if (
            step_info.op == server_lib.Opcode.STEP_RUN
            and self._request.ctx.disable_immediate_execution is True
            and not is_targeting_enabled
        ):
            # We should only get here when encountering a new, single step.run
            # after parallel steps

            step_info.op = server_lib.Opcode.PLANNED

            raise step_lib.ResponseInterrupt(
                step_lib.StepResponse(step=step_info)
            )

        if step_info.op == server_lib.Opcode.STEP_RUN:
            return step

        raise step_lib.ResponseInterrupt(step_lib.StepResponse(step=step_info))

    def run(
        self,
        client: client_lib.Inngest,
        ctx: ContextSync,
        handler: FunctionHandlerSync[types.T],
        fn: function.Function[types.T],
        output_type: object = types.EmptySentinel,
    ) -> CallResult:
        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        middleware_err = self._middleware.transform_input_sync(
            ctx, fn, self._memos
        )
        if isinstance(middleware_err, Exception):
            return CallResult(middleware_err)

        # No memoized data means we're calling the function for the first time.
        if self._memos.size == 0:
            err = self._middleware.before_execution_sync()
            if isinstance(err, Exception):
                return CallResult(err)

        try:
            try:
                output: object = handler(ctx)

                # Even though output_type isn't used, we still check for it to
                # ensure users are adding explicit types on functions that
                # return non-JSON-serializable data (e.g. Pydantic objects). If
                # we didn't do this, then `step.invoke` would not return the
                # correct type at runtime.
                if (
                    client._serializer is not None
                    and output_type is not types.EmptySentinel
                ):
                    output = client._serializer.serialize(output)
            except Exception as user_err:
                transforms.remove_first_traceback_frame(user_err)
                raise UserError(user_err)

            err = self._middleware.after_execution_sync()
            if isinstance(err, Exception):
                return CallResult(err)

            return CallResult(output=output)
        except step_lib.ResponseInterrupt as interrupt:
            err = self._middleware.after_execution_sync()
            if isinstance(err, Exception):
                return CallResult(err)

            return CallResult.from_responses(interrupt.responses)
        except UserError as err:
            return CallResult(err.err)
        except step_lib.SkipInterrupt as err:
            # This should only happen in a non-deterministic scenario, where
            # step targeting is enabled and an unexpected step is encountered.
            # We don't currently have a way to recover from this scenario.

            return CallResult(
                errors.StepUnexpectedError(
                    f'found step "{err.step_id}" when targeting a different step'
                )
            )
        except Exception as err:
            return CallResult(err)
