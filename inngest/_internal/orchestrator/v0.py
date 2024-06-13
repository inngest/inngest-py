from __future__ import annotations

import asyncio
import typing

from inngest._internal import errors, execution, step_lib, transforms, types

from .utils import is_function_handler_async, is_function_handler_sync

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, function, middleware_lib


class OrchestratorV0:
    version = "0"

    def __init__(
        self,
        memos: step_lib.StepMemos,
        middleware: middleware_lib.MiddlewareManager,
        target_hashed_id: typing.Optional[str],
    ) -> None:
        self._memos = memos
        self._middleware = middleware
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
        inside_parallel: bool,
    ) -> execution.ReportedStep:
        step_signal = asyncio.Future[execution.ReportedStep]()

        step = execution.ReportedStep(step_signal, step_info)
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
        if inside_parallel and not is_targeting_enabled:
            if step_info.op == step_lib.Opcode.STEP_RUN:
                step_info.op = step_lib.Opcode.PLANNED

            # Plan this step because we're in parallel mode.
            raise step_lib.ResponseInterrupt(
                step_lib.StepResponse(step=step_info)
            )

        if step_info.op == step_lib.Opcode.STEP_RUN:
            return step

        raise step_lib.ResponseInterrupt(step_lib.StepResponse(step=step_info))

    async def run(
        self,
        client: client_lib.Inngest,
        ctx: execution.Context,
        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ],
        fn: function.Function,
    ) -> execution.CallResult:
        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        middleware_err = await self._middleware.transform_input(
            ctx,
            fn,
            self._memos,
        )
        if isinstance(middleware_err, Exception):
            return execution.CallResult(middleware_err)

        # No memoized data means we're calling the function for the first time.
        if self._memos.size == 0:
            err = await self._middleware.before_execution()
            if isinstance(err, Exception):
                return execution.CallResult(err)

        try:
            output: object

            try:
                # # Determine whether the handler is async (i.e. if we need to await
                # # it). Sync functions are OK in async contexts, so it's OK if the
                # # handler is sync.
                if is_function_handler_async(handler):
                    output = await handler(
                        ctx=ctx,
                        step=step_lib.Step(
                            client,
                            self,
                            self._memos,
                            self._middleware,
                            step_lib.StepIDCounter(),
                            self._target_hashed_id,
                        ),
                    )
                elif is_function_handler_sync(handler):
                    output = handler(
                        ctx=ctx,
                        step=step_lib.StepSync(
                            client,
                            self._memos,
                            self._middleware,
                            step_lib.StepIDCounter(),
                            self._target_hashed_id,
                        ),
                    )
                else:
                    # Should be unreachable but Python's custom type guards don't
                    # support negative checks :(
                    return execution.CallResult(
                        errors.UnknownError(
                            "unable to determine function handler type"
                        )
                    )
            except Exception as user_err:
                transforms.remove_first_traceback_frame(user_err)
                raise execution.UserError(user_err)

            err = await self._middleware.after_execution()
            if isinstance(err, Exception):
                return execution.CallResult(err)

            return execution.CallResult(output=output)
        except step_lib.ResponseInterrupt as interrupt:
            err = await self._middleware.after_execution()
            if isinstance(err, Exception):
                return execution.CallResult(err)

            return execution.CallResult.from_responses(interrupt.responses)
        except execution.UserError as err:
            return execution.CallResult(err.err)
        except step_lib.SkipInterrupt as err:
            # This should only happen in a non-deterministic scenario, where
            # step targeting is enabled and an unexpected step is encountered.
            # We don't currently have a way to recover from this scenario.

            return execution.CallResult(
                errors.StepUnexpectedError(
                    f'found step "{err.step_id}" when targeting a different step'
                )
            )
        except Exception as err:
            return execution.CallResult(err)


class OrchestratorV0Sync:
    version = "0"

    def __init__(
        self,
        memos: step_lib.StepMemos,
        middleware: middleware_lib.MiddlewareManager,
        target_hashed_id: typing.Optional[str],
    ) -> None:
        self._memos = memos
        self._middleware = middleware
        self._target_hashed_id = target_hashed_id

    def run(
        self,
        client: client_lib.Inngest,
        ctx: execution.Context,
        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ],
        fn: function.Function,
    ) -> execution.CallResult:
        # Give middleware the opportunity to change some of params passed to the
        # user's handler.
        middleware_err = self._middleware.transform_input_sync(
            ctx, fn, self._memos
        )
        if isinstance(middleware_err, Exception):
            return execution.CallResult(middleware_err)

        # No memoized data means we're calling the function for the first time.
        if self._memos.size == 0:
            err = self._middleware.before_execution_sync()
            if isinstance(err, Exception):
                return execution.CallResult(err)

        try:
            if is_function_handler_sync(handler):
                try:
                    output: object = handler(
                        ctx=ctx,
                        step=step_lib.StepSync(
                            client,
                            self._memos,
                            self._middleware,
                            step_lib.StepIDCounter(),
                            self._target_hashed_id,
                        ),
                    )
                except Exception as user_err:
                    transforms.remove_first_traceback_frame(user_err)
                    raise execution.UserError(user_err)
            else:
                return execution.CallResult(
                    errors.AsyncUnsupportedError(
                        "encountered async function in non-async context"
                    )
                )

            err = self._middleware.after_execution_sync()
            if isinstance(err, Exception):
                return execution.CallResult(err)

            return execution.CallResult(output=output)
        except step_lib.ResponseInterrupt as interrupt:
            err = self._middleware.after_execution_sync()
            if isinstance(err, Exception):
                return execution.CallResult(err)

            return execution.CallResult.from_responses(interrupt.responses)
        except execution.UserError as err:
            return execution.CallResult(err.err)
        except step_lib.SkipInterrupt as err:
            # This should only happen in a non-deterministic scenario, where
            # step targeting is enabled and an unexpected step is encountered.
            # We don't currently have a way to recover from this scenario.

            return execution.CallResult(
                errors.StepUnexpectedError(
                    f'found step "{err.step_id}" when targeting a different step'
                )
            )
        except Exception as err:
            return execution.CallResult(err)
