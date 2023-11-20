from __future__ import annotations

import threading

from inngest._internal import (
    client_lib,
    execution,
    middleware_lib,
    transforms,
    types,
)


class StepMemos:
    """Holds memoized step output."""

    @property
    def size(self) -> int:
        return len(self._memos)

    def __init__(self, memos: dict[str, execution.Output]) -> None:
        self._memos = memos

    def pop(self, hashed_id: str) -> execution.Output | types.EmptySentinel:
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
            output = execution.Output.from_raw(v)
            if isinstance(output, Exception):
                # Not all steps nest their output in an Output-compatible object
                # (i.e. they don't nest output in a data field). For example,
                # `step.run` nests its output in a data field but
                # `step.waitForEvent` will not nest its fulfilling event.
                output = execution.Output(data=v)

            memos[k] = output
        return cls(memos)


class StepBase:
    def __init__(
        self,
        client: client_lib.Inngest,
        memos: StepMemos,
        middleware: middleware_lib.MiddlewareManager,
        step_id_counter: StepIDCounter,
        target_hashed_id: str | None,
    ) -> None:
        self._client = client
        self._inside_parallel = False
        self._memos = memos
        self._middleware = middleware
        self._step_id_counter = step_id_counter
        self._target_hashed_id = target_hashed_id

    def _get_hashed_id(self, step_id: str) -> str:
        id_count = self._step_id_counter.increment(step_id)
        if id_count > 1:
            step_id = f"{step_id}:{id_count - 1}"
        return transforms.hash_step_id(step_id)

    async def _get_memo(
        self,
        hashed_id: str,
    ) -> execution.Output | types.EmptySentinel:
        memo = self._memos.pop(hashed_id)

        # If there are no more memos then all future code is new.
        if self._memos.size == 0:
            await self._middleware.before_execution()

        return memo

    def _get_memo_sync(
        self,
        hashed_id: str,
    ) -> execution.Output | types.EmptySentinel:
        memo = self._memos.pop(hashed_id)

        # If there are no more memos then all future code is new.
        if self._memos.size == 0:
            self._middleware.before_execution_sync()

        return memo


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
        responses: execution.StepResponse | list[execution.StepResponse],
    ) -> None:
        if not isinstance(responses, list):
            responses = [responses]
        self.responses = responses


class SkipInterrupt(BaseException):
    pass


class WaitForEventOpts(types.BaseModel):
    if_exp: str | None
    timeout: str
