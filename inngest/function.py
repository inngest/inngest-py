from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import traceback
from typing import Callable, TypeVar
import uuid

from .types import (
    ActionError,
    ActionResponse,
    FunctionCall,
    FunctionConfig,
    FunctionHandler,
    MemoizedStep,
    Opcode,
    Runtime,
    StepConfig,
    StepConfigRetries,
    TriggerCron,
    TriggerEvent,
)


T = TypeVar("T")


class NonRetriableError(Exception):
    pass


def create_function(
    opts: FunctionOpts,
    trigger: TriggerCron | TriggerEvent,
) -> Callable[[FunctionHandler], Function]:
    def decorator(func: FunctionHandler) -> Function:
        return Function(opts, trigger, func)

    return decorator


@dataclass
class FunctionOpts:
    id: str
    name: str | None = None
    retries: int | None = None


class Function:
    def __init__(
        self,
        opts: FunctionOpts,
        trigger: TriggerCron | TriggerEvent,
        handler: FunctionHandler,
    ) -> None:
        self._handler = handler
        self._opts = opts
        self._trigger = trigger

    def call(
        self,
        call: FunctionCall,
    ) -> list[ActionResponse] | str | ActionError:
        memoized_stack = [
            call.steps.get(step_run_id) for step_run_id in call.ctx.stack.stack
        ]

        step = Step(memoized_stack)

        try:
            res = self._handler(event=call.event, step=step)
            return json.dumps(res)
        except EarlyReturn as out:
            return [
                ActionResponse(
                    data=out.data,  # type: ignore
                    display_name=out.display_name,
                    id=out.action_id,
                    name=out.name,
                    op=out.op,
                )
            ]
        except Exception as err:
            is_retriable = isinstance(err, NonRetriableError) is False

            return ActionError(
                is_retriable=is_retriable,
                message=str(err),
                name=type(err).__name__,
                stack=traceback.format_exc(),
            )

    def get_config(self) -> FunctionConfig:
        fn_id = self._opts.id

        name = fn_id
        if self._opts.name is not None:
            name = self._opts.name

        retries: StepConfigRetries | None = None
        if self._opts.retries is not None:
            retries = StepConfigRetries(
                attempts=self._opts.retries + 1,
            )

        return FunctionConfig(
            id=fn_id,
            name=name,
            steps={
                "step": StepConfig(
                    id="step",
                    name="step",
                    retries=retries,
                    runtime=Runtime(
                        type="http",
                        url=f"http://localhost:8000/api/inngest?fnId={fn_id}&stepId=step",
                    ),
                ),
            },
            triggers=[self._trigger],
        )

    def get_id(self) -> str:
        return self._opts.id


# Extend BaseException to avoid being caught by the user's code. Users can still
# catch it if they do a "bare except", but that's a known antipattern in the
# Python world.
class EarlyReturn(BaseException):
    def __init__(
        self,
        *,
        action_id: str,
        data: object = None,
        display_name: str,
        name: str,
        op: Opcode,
    ) -> None:
        self.action_id = action_id
        self.data = data
        self.display_name = display_name
        self.name = name
        self.op = op


EmptySentinel = object()


class Step:
    def __init__(self, memoized_stack: list[MemoizedStep | None]) -> None:
        self._memoized_stack = memoized_stack
        self._stack_index = -1

    def _get_memo(self) -> object:
        if (
            self._stack_index < len(self._memoized_stack)
            and self._memoized_stack[self._stack_index] is not None
        ):
            return self._memoized_stack[self._stack_index].data  # type: ignore

        return EmptySentinel

    def run(
        self,
        id: str,  # pylint: disable=redefined-builtin
        handler: Callable[[], T],
    ) -> T:
        self._stack_index += 1

        memo = self._get_memo()
        if memo is not EmptySentinel:
            return memo  # type: ignore

        raise EarlyReturn(
            action_id=uuid.uuid4().hex,
            data=handler(),
            display_name=id,
            op=Opcode.Step,
            name=id,
        )

    def sleep_until(
        self,
        id: str,  # pylint: disable=redefined-builtin
        time: datetime,
    ) -> None:
        self._stack_index += 1

        memo = self._get_memo()
        if memo is not EmptySentinel:
            return memo  # type: ignore

        raise EarlyReturn(
            action_id=uuid.uuid4().hex,
            display_name=id,
            name=to_iso_utc(time),
            op=Opcode.Sleep,
        )


def to_iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
