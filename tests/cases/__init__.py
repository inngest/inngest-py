import inngest

from . import (
    event_payload,
    function_args,
    no_steps,
    on_failure,
    sleep_until,
    two_steps,
    unserializable_step_output,
    wait_for_event_fulfill,
    wait_for_event_timeout,
)
from .base import Case


def create_cases(client: inngest.Inngest, framework: str) -> list[Case]:
    return [
        case.create(client, framework)
        for case in (
            event_payload,
            function_args,
            no_steps,
            on_failure,
            sleep_until,
            two_steps,
            unserializable_step_output,
            wait_for_event_fulfill,
            wait_for_event_timeout,
        )
    ]


__all__ = ["create_cases"]
