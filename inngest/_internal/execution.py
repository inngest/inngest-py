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
    stack: str

    @classmethod
    def from_error(cls, err: Exception) -> CallError:
        return cls(
            is_internal=isinstance(err, errors.InternalError),
            is_retriable=isinstance(err, errors.NonRetriableError) is False,
            message=str(err),
            name=type(err).__name__,
            original_error=err,
            stack=transforms.get_traceback(err),
        )


class FunctionCallResponse(types.BaseModel):
    """When a function successfully returns."""

    data: object


class StepResponse(types.BaseModel):
    data: Output | None = None
    display_name: str
    id: str
    name: str
    op: Opcode
    opts: dict[str, object] | None = None


class Output(types.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")

    data: object = None
    error: object = None


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
    PLANNED = "StepPlanned"
    SLEEP = "Sleep"
    STEP = "Step"
    WAIT_FOR_EVENT = "WaitForEvent"


# If the Executor sends this step ID then it isn't targeting a specific step.
UNSPECIFIED_STEP_ID = "step"
