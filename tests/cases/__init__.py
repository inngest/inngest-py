import inngest

from . import (
    base,
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


def create_cases(client: inngest.Inngest, framework: str) -> list[base.Case]:
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
