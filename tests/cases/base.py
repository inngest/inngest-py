import time
from dataclasses import dataclass
from typing import Callable

import inngest


class BaseState:
    def is_done(self) -> bool:
        raise NotImplementedError()


@dataclass
class Case:
    event_name: str
    fn: inngest.Function
    name: str
    run_test: Callable[[object], None]
    state: BaseState


def wait_for(
    assertion: Callable[[], None],
    timeout: int = 5,
) -> None:
    start = time.time()
    while True:
        try:
            assertion()
            return
        except Exception as err:
            timed_out = time.time() - start > timeout
            if timed_out:
                raise err

        time.sleep(0.2)
