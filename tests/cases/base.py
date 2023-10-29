import dataclasses
import datetime
import time
import typing

import inngest


class BaseState:
    run_id: str | None = None

    def wait_for_run_id(
        self,
        *,
        timeout: datetime.timedelta = datetime.timedelta(seconds=5),
    ) -> str:
        def assertion() -> None:
            assert self.run_id is not None

        wait_for(assertion, timeout=timeout)
        assert self.run_id is not None
        return self.run_id


@dataclasses.dataclass
class Case:
    event_name: str
    fn: inngest.Function
    name: str
    run_test: typing.Callable[[object], None]
    state: BaseState


def wait_for(
    assertion: typing.Callable[[], None],
    *,
    timeout: datetime.timedelta = datetime.timedelta(seconds=5),
) -> None:
    start = datetime.datetime.now()
    while True:
        try:
            assertion()
            return
        except Exception as err:
            # timed_out = time.time() - start > timeout
            timed_out = datetime.datetime.now() > start + timeout
            if timed_out:
                raise err

        time.sleep(0.2)
