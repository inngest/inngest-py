from __future__ import annotations

import dataclasses
import enum
import typing

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


@dataclasses.dataclass
class TransformableCallInput:
    logger: types.Logger


class CallError(types.BaseModel):
    """
    When an error that occurred during a call. Used for both function- and step-level
    errors.
    """

    is_internal: bool
    is_retriable: bool
    message: str
    name: str
    stack: str

    @classmethod
    def from_error(cls, err: Exception) -> CallError:
        return cls(
            is_internal=isinstance(err, errors.InternalError),
            is_retriable=isinstance(err, errors.NonRetriableError) is False,
            message=str(err),
            name=type(err).__name__,
            stack=transforms.get_traceback(err),
        )


class FunctionCallResponse(types.BaseModel):
    """
    When a function successfully returns.
    """

    data: types.Serializable


class StepCallResponse(types.BaseModel):
    """
    When a step successfully returns.
    """

    data: types.Serializable
    display_name: str
    id: str
    name: str
    op: Opcode
    opts: dict[str, object] | None = None


def is_step_call_responses(
    value: object,
) -> typing.TypeGuard[list[StepCallResponse]]:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, StepCallResponse) for item in value)


CallResult: typing.TypeAlias = (
    list[StepCallResponse] | FunctionCallResponse | CallError
)


class Opcode(enum.Enum):
    SLEEP = "Sleep"
    STEP = "Step"
    WAIT_FOR_EVENT = "WaitForEvent"
