from __future__ import annotations

import dataclasses
import enum
import typing

import pydantic
import typing_extensions

from . import event_lib, transforms, types


class Call(types.BaseModel):
    ctx: CallContext
    event: event_lib.Event
    events: typing.Optional[list[event_lib.Event]] = None
    steps: dict[str, object]
    use_api: bool


class CallContext(types.BaseModel):
    attempt: int
    run_id: str
    stack: CallStack


class CallStack(types.BaseModel):
    stack: list[str]


class StepInfo(types.BaseModel):
    display_name: str = pydantic.Field(..., serialization_alias="displayName")
    id: str

    # Deprecated
    name: typing.Optional[str] = None

    op: Opcode
    opts: typing.Optional[dict[str, object]] = None


class StepResponse(types.BaseModel):
    output: object = None
    original_error: object = pydantic.Field(default=None, exclude=True)
    step: StepInfo


class MemoizedError(types.BaseModel):
    message: str
    name: str
    stack: typing.Optional[str] = None

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
    error: typing.Optional[MemoizedError] = None


def is_step_call_responses(
    value: object,
) -> typing_extensions.TypeGuard[list[StepResponse]]:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, StepResponse) for item in value)


@dataclasses.dataclass
class CallResult:
    error: typing.Optional[Exception] = None

    # Multiple results from a single call (only used for steps). This will only
    # be longer than 1 for parallel steps. Otherwise, it will be 1 long for
    # sequential steps
    multi: typing.Optional[list[CallResult]] = None

    # Need a sentinel value to differentiate between None and unset
    output: object = types.empty_sentinel

    # Step metadata (e.g. user-specified ID)
    step: typing.Optional[StepInfo] = None

    @property
    def is_empty(self) -> bool:
        return all(
            [
                self.error is None,
                self.multi is None,
                self.output is types.empty_sentinel,
                self.step is None,
            ]
        )

    @classmethod
    def from_responses(
        cls,
        responses: list[StepResponse],
    ) -> CallResult:
        multi = []

        for response in responses:
            error = None
            if isinstance(response.original_error, Exception):
                error = response.original_error

            multi.append(
                cls(
                    error=error,
                    output=response.output,
                    step=response.step,
                )
            )

        return cls(multi=multi)


class Opcode(enum.Enum):
    INVOKE = "InvokeFunction"
    PLANNED = "StepPlanned"
    SLEEP = "Sleep"
    STEP_RUN = "StepRun"
    STEP_ERROR = "StepError"
    WAIT_FOR_EVENT = "WaitForEvent"


# If the Executor sends this step ID then it isn't targeting a specific step.
UNSPECIFIED_STEP_ID = "step"
