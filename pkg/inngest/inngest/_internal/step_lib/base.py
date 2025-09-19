from __future__ import annotations

import dataclasses
import threading
import typing

import pydantic

from inngest._internal import (
    client_lib,
    middleware_lib,
    server_lib,
    transforms,
    types,
)


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


class StepMemos:
    """Holds memoized step output."""

    @property
    def size(self) -> int:
        return len(self._memos)

    def __init__(self, memos: dict[str, Output]) -> None:
        self._memos = memos

    def values(self) -> typing.Iterator[Output]:
        return iter(self._memos.values())

    def pop(self, hashed_id: str) -> typing.Union[Output, types.EmptySentinel]:
        if hashed_id in self._memos:
            memo = self._memos[hashed_id]

            # Remove memo
            self._memos = {
                k: v for k, v in self._memos.items() if k != hashed_id
            }

            return memo

        return types.empty_sentinel

    @classmethod
    def from_raw(cls, raw: dict[str, object]) -> StepMemos:
        memos = {}
        for k, v in raw.items():
            output = Output.from_raw(v)
            if isinstance(output, Exception):
                # Not all steps nest their output in an Output-compatible object
                # (i.e. they don't nest output in a data field). For example,
                # `step.run` nests its output in a data field but
                # `step.waitForEvent` will not nest its fulfilling event.
                output = Output(data=v)

            memos[k] = output
        return cls(memos)


class StepBase:
    def __init__(
        self,
        client: client_lib.Inngest,
        middleware: middleware_lib.MiddlewareManager,
        step_id_counter: StepIDCounter,
        target_hashed_id: typing.Optional[str],
    ) -> None:
        self._client = client
        self._middleware = middleware
        self._step_id_counter = step_id_counter
        self._target_hashed_id = target_hashed_id

    def _handle_skip(
        self,
        parsed_step_id: ParsedStepID,
    ) -> None:
        """
        Handle a skip interrupt. Step targeting is enabled and this step is not
        the target then skip the step.
        """

        is_targeting_enabled = self._target_hashed_id is not None
        is_targeted = self._target_hashed_id == parsed_step_id.hashed
        if is_targeting_enabled and not is_targeted:
            # Skip this step because a different step is targeted.
            raise SkipInterrupt(parsed_step_id.user_facing)

    def _parse_step_id(self, step_id: str) -> ParsedStepID:
        """
        Parse a user-specified step ID into a hashed ID and a deduped
        user-facing step ID.
        """

        id_count = self._step_id_counter.increment(step_id)
        if id_count > 1:
            step_id = f"{step_id}:{id_count - 1}"

        return ParsedStepID(
            hashed=transforms.hash_step_id(step_id),
            user_facing=step_id,
        )


@dataclasses.dataclass
class ParsedStepID:
    hashed: str
    user_facing: str


class StepIDCounter:
    """
    Counts the number of times a step ID has been used. We support reused step
    IDs so we need a way to keep track of their counts.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._mutex = threading.Lock()

    def increment(self, hashed_id: str) -> int:
        with self._mutex:
            if hashed_id not in self._counts:
                self._counts[hashed_id] = 0

            self._counts[hashed_id] += 1
            return self._counts[hashed_id]


class ResponseInterrupt(BaseException):
    """
    Extend BaseException to avoid being caught by the user's code. Users can
    still catch it if they do a "bare except", but that's a known antipattern in
    the Python world.
    """

    def __init__(
        self,
        responses: typing.Union[StepResponse, list[StepResponse]],
    ) -> None:
        if not isinstance(responses, list):
            responses = [responses]
        self.responses = responses

    def set_step_info(self, step_info: StepInfo) -> None:
        """
        Set the step info on all responses. This is useful for catching nested
        steps, since we want to report the "parent" step info and not the
        "child" step info.
        """

        for response in self.responses:
            response.step = step_info


class SkipInterrupt(BaseException):
    def __init__(self, step_id: str) -> None:
        self.step_id = step_id


class NestedStepInterrupt(BaseException):
    pass


class InvokeOpts(types.BaseModel):
    function_id: str
    payload: InvokeOptsPayload
    timeout: typing.Optional[str]


class InvokeOptsPayload(types.BaseModel):
    data: object
    v: typing.Optional[str]


class WaitForEventOpts(types.BaseModel):
    if_exp: typing.Optional[str] = pydantic.Field(..., serialization_alias="if")
    timeout: str


class AIInferOpts(types.BaseModel):
    auth_key: str
    body: dict[str, object]
    format: str
    headers: dict[str, str]
    type: str = "step.ai.infer"
    url: str | None = None


class StepInfo(types.BaseModel):
    display_name: str = pydantic.Field(..., serialization_alias="displayName")
    id: str

    # Deprecated
    name: typing.Optional[str] = None

    op: server_lib.Opcode
    opts: typing.Optional[dict[str, object]] = None

    def set_parallel_mode(self, parallel_mode: server_lib.ParallelMode) -> None:
        if parallel_mode != server_lib.ParallelMode.RACE:
            # Nothing to do because race mode is opt-in
            return

        if self.opts is None:
            self.opts = {}
        self.opts[server_lib.OptKey.PARALLEL_MODE.value] = parallel_mode.value


class StepResponse(types.BaseModel):
    output: object = None
    original_error: object = pydantic.Field(default=None, exclude=True)
    step: StepInfo
