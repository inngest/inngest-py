from __future__ import annotations

import enum
import typing

import pydantic

from . import errors, event_lib, transforms, types


class Call(types.BaseModel):
    ctx: CallContext
    event: event_lib.Event
    events: list[event_lib.Event]
    steps: dict[str, object]


class CallContext(types.BaseModel):
    attempt: int
    run_id: str
    stack: CallStack


class CallStack(types.BaseModel):
    stack: list[str]


class CallError(types.BaseModel):
    """
    When an error that occurred during a call. Used for both function- and step-level
    errors.
    """

    is_internal: bool
    is_retriable: bool
    message: str
    name: str
    original_error: object = pydantic.Field(exclude=True)
    stack: str | None
    step_id: str | None

    @classmethod
    def from_error(
        cls,
        err: Exception,
        step_id: str | None = None,
    ) -> CallError:
        if isinstance(err, errors.Error):
            is_retriable = err.is_retriable
            message = err.message
            name = err.name
            stack = err.stack
        else:
            is_retriable = True
            message = str(err)
            name = type(err).__name__
            stack = transforms.get_traceback(err)

        return cls(
            is_internal=isinstance(err, errors.InternalError),
            is_retriable=is_retriable,
            message=message,
            name=name,
            original_error=err,
            stack=stack,
            step_id=step_id,
        )


class FunctionCallResponse(types.BaseModel):
    """When a function successfully returns."""

    data: object


class StepResponse(types.BaseModel):
    data: Output | None = None
    display_name: str = pydantic.Field(..., serialization_alias="displayName")
    id: str

    # Deprecated
    name: str | None = None

    op: Opcode
    opts: dict[str, object] | None = None


class MemoizedError(types.BaseModel):
    message: str
    name: str
    stack: str | None

    @classmethod
    def from_error(cls, err: Exception) -> MemoizedError:
        return cls(
            message=str(err),
            name=type(err).__name__,
            stack=transforms.get_traceback(err),
        )


class Output(types.BaseModel):
    # Fail validation if any extra fields exist, because this will prevent
    # accidentally assuming user data is nested data
    model_config = pydantic.ConfigDict(extra="forbid")

    data: object = None

    # TODO: Change the type to MemoizedError. But that requires a breaking
    # change, so do it in version 0.4
    error: dict[str, object] | None = None


def is_step_call_responses(
    value: object,
) -> typing.TypeGuard[list[StepResponse]]:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, StepResponse) for item in value)


CallResult: typing.TypeAlias = (
    list[StepResponse] | FunctionCallResponse | CallError
)


class Opcode(enum.Enum):
    INVOKE = "InvokeFunction"
    PLANNED = "StepPlanned"
    SLEEP = "Sleep"
    STEP_RUN = "StepRun"
    STEP_ERROR = "StepError"
    WAIT_FOR_EVENT = "WaitForEvent"


# If the Executor sends this step ID then it isn't targeting a specific step.
UNSPECIFIED_STEP_ID = "step"
