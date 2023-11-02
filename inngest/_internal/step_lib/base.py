from __future__ import annotations

import threading

from inngest._internal import execution, transforms, types


class StepBase:
    _memos: dict[str, object]
    _step_id_counter: StepIDCounter

    def _get_hashed_id(self, step_id: str) -> str:
        id_count = self._step_id_counter.increment(step_id)
        if id_count > 1:
            step_id = f"{step_id}:{id_count - 1}"
        return transforms.hash_step_id(step_id)

    def _get_memo(self, hashed_id: str) -> object:
        if hashed_id in self._memos:
            return self._memos[hashed_id]

        return types.EmptySentinel


class StepIDCounter:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._mutex = threading.Lock()

    def increment(self, hashed_id: str) -> int:
        with self._mutex:
            if hashed_id not in self._counts:
                self._counts[hashed_id] = 0

            self._counts[hashed_id] += 1
            return self._counts[hashed_id]


# Extend BaseException to avoid being caught by the user's code. Users can still
# catch it if they do a "bare except", but that's a known antipattern in the
# Python world.
class Interrupt(BaseException):
    def __init__(
        self,
        *,
        data: types.Serializable = None,
        display_name: str,
        hashed_id: str,
        name: str,
        op: execution.Opcode,
        opts: dict[str, object] | None = None,
    ) -> None:
        """
        Args:
            data: JSON returned by the step.
            display_name: User-specified step ID.
            hashed_id: Hashed step ID.
        """

        self.data = data
        self.display_name = display_name
        self.hashed_id = hashed_id
        self.name = name
        self.op = op
        self.opts = opts


class WaitForEventOpts(types.BaseModel):
    if_exp: str | None
    timeout: str
