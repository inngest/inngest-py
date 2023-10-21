from dataclasses import dataclass
from typing import Callable

import inngest

from .base import wait_for


class _BaseState:
    def is_done(self) -> bool:
        raise NotImplementedError()


@dataclass
class Case:
    event_name: str
    fn: inngest.Function
    name: str
    run_test: Callable[[object], None]
    state: _BaseState


def _no_steps(client: inngest.Inngest, framework: str) -> Case:
    name = "no_steps"
    event_name = f"{framework}/{name}"

    class State(_BaseState):
        counter = 0

        def is_done(self) -> bool:
            return self.counter == 1

    state = State()

    @inngest.create_function(
        inngest.FunctionOpts(id=name),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(**_kwargs: object) -> None:
        state.counter += 1

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        def assertion() -> None:
            assert state.is_done()

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=name,
    )


def _two_steps(client: inngest.Inngest, framework: str) -> Case:
    name = "two_steps"
    event_name = f"{framework}/{name}"

    class State(_BaseState):
        step_1_counter = 0
        step_2_counter = 0
        end_counter = 0

        def is_done(self) -> bool:
            return (
                self.step_1_counter == 1
                and self.step_2_counter == 1
                and self.end_counter == 1
            )

    state = State()

    @inngest.create_function(
        inngest.FunctionOpts(id=name),
        inngest.TriggerEvent(event=event_name),
    )
    def fn(*, step: inngest.Step, **_kwargs: object) -> None:
        def step_1() -> str:
            state.step_1_counter += 1
            return "hi"

        step.run("step_1", step_1)

        def step_2() -> None:
            state.step_2_counter += 1

        step.run("step_2", step_2)
        state.end_counter += 1

    def run_test(_self: object) -> None:
        client.send(inngest.Event(name=event_name))

        def assertion() -> None:
            assert state.is_done()

        wait_for(assertion)

    return Case(
        event_name=event_name,
        fn=fn,
        run_test=run_test,
        state=state,
        name=name,
    )


def create_cases(client: inngest.Inngest, framework: str) -> list[Case]:
    return [
        _no_steps(client, framework),
        _two_steps(client, framework),
    ]
