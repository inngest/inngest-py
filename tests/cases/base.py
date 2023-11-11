import dataclasses
import datetime
import time
import typing

import inngest


class TestClass(typing.Protocol):
    client: inngest.Inngest


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
    run_test: typing.Callable[[TestClass], None]
    state: BaseState


def create_event_name(
    framework: str,
    test_name: str,
    is_sync: bool,
) -> str:
    event_name = f"{framework}/{test_name}"
    if is_sync:
        event_name += "_sync"
    return event_name


def create_test_name(
    test_name: str,
    is_sync: bool,
) -> str:
    if is_sync:
        test_name += "_sync"
    return test_name


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
            timed_out = datetime.datetime.now() > start + timeout
            if timed_out:
                raise err

        time.sleep(0.2)
