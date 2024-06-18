from __future__ import annotations

import asyncio
import typing

from inngest._internal import (
    errors,
    execution,
    server_lib,
    step_lib,
    transforms,
    types,
)

from .utils import (
    is_function_handler_async,
    is_function_handler_sync,
    wait_for_next_loop,
)

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, function, middleware_lib


class OrchestratorExperimental:
    version = "experimental"

    def __init__(
        self,
        memos: step_lib.StepMemos,
        middleware: middleware_lib.MiddlewareManager,
        stack: list[str],
        target_hashed_id: typing.Optional[str],
    ) -> None:
        self._memos = memos
        self._middleware = middleware
        self._pending_steps: dict[str, execution.ReportedStep] = {}
        self._skipped_steps: list[execution.ReportedStep] = []
        self._staged_steps: list[execution.ReportedStep] = []
        self._stack = stack
        self._target_hashed_id = target_hashed_id

    async def report_step(
        self,
        step_info: step_lib.StepInfo,
        inside_parallel: bool,
    ) -> execution.ReportedStep:
        step_signal = asyncio.Future[execution.ReportedStep]()
        self._pending_steps[step_info.id] = execution.ReportedStep(
            step_signal, step_info
        )
        step_count = len(self._pending_steps)
        await wait_for_next_loop()

        is_done_reporting = step_count == len(self._pending_steps)
        if is_done_reporting:
            await self._process_steps()
            await self._release_steps()

        return await step_signal

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
            ctx, fn, self._memos
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
                # Determine whether the handler is async (i.e. if we need to
                # await it). Sync functions are OK in async contexts, so it's OK
                # if the handler is sync.
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
        finally:
            await self._post_run_cleanup()

    async def _apply_memos(self) -> None:
        for step in self._pending_steps.values():
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

    async def _post_run_cleanup(self) -> None:
        """
        Cleanup any skipped or pending steps that were not released. This avoids
        async leaks
        """

        await asyncio.gather(
            *[step.release_and_skip() for step in self._skipped_steps],
        )

        await asyncio.gather(
            *[step.release_and_skip() for step in self._pending_steps.values()],
        )

    async def _process_steps(self) -> None:
        """
        Apply memoized data, plan steps, and order steps for execution
        """

        targeted_step = None
        if self._target_hashed_id is not None:
            for step in list(self._pending_steps.values()):
                if step.info.id == self._target_hashed_id:
                    targeted_step = step

        if targeted_step is not None:
            self._staged_steps = [targeted_step]

            for step in list(self._pending_steps.values()):
                self._skipped_steps.append(step)
                self._pending_steps.pop(step.info.id)

            # End early since we only want to run the targeted step
            return

        await self._apply_memos()
        self._plan()
        self._stage()

    async def _release_steps(self) -> None:
        """
        Orchestrate the release of all staged steps
        """

        if len(self._staged_steps) == 0:
            # Unreachable
            raise Exception("no staged steps to release")

        for i, step in enumerate(self._staged_steps):
            if i > 0:
                prev_step = self._staged_steps[i - 1]

                # Release this step when the previous step is done
                prev_step.on_done(step.release)

        # Release the first step to start the chain of ordered releases
        await self._staged_steps[0].release()

        # All steps are released, so we can clear the staged steps
        self._staged_steps = []

    def _plan(self) -> None:
        plans = []

        for step in list(self._pending_steps.values()):
            is_memoized = step.error is not None or not isinstance(
                step.output, types.EmptySentinel
            )
            if not is_memoized:
                if step.info.op == server_lib.Opcode.STEP_RUN:
                    step.info.op = server_lib.Opcode.PLANNED
                plans.append(step_lib.StepResponse(step=step.info))

        if len(plans) > 0:
            raise step_lib.ResponseInterrupt(plans)

    def _stage(self) -> None:
        """
        Stages steps for execution in the proper order
        """

        def sort_key(step: execution.ReportedStep) -> int:
            try:
                return self._stack.index(step.info.id)
            except ValueError:
                # Unreachable
                raise Exception(f"step {step.info.id} not found in stack")

        self._staged_steps = sorted(self._pending_steps.values(), key=sort_key)

        for step in self._staged_steps:
            self._pending_steps.pop(step.info.id)


class ExecutionV0Sync:
    def __init__(
        self,
        memos: step_lib.StepMemos,
        middleware: middleware_lib.MiddlewareManager,
    ) -> None:
        self._condition = asyncio.Condition()
        self._memos = memos
        self._middleware = middleware
        self._pending_report_count = 0

    def run(
        self,
        client: client_lib.Inngest,
        ctx: execution.Context,
        handler: typing.Union[
            execution.FunctionHandlerAsync, execution.FunctionHandlerSync
        ],
        fn: function.Function,
        target_hashed_id: typing.Optional[str],
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
                            target_hashed_id,
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
