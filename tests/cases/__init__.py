import inngest

from . import (
    base,
    cancel,
    debounce,
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


def create_cases(
    client: inngest.Inngest,
    framework: str,
) -> list[base.Case[inngest.Function]]:
    return [
        case.create(client, framework, is_sync=False)
        for case in (
            cancel,
            debounce,
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


def create_cases_sync(
    client: inngest.Inngest,
    framework: str,
) -> list[base.Case[inngest.FunctionSync]]:
    return [
        case.create(client, framework, is_sync=True)
        for case in (
            cancel,
            debounce,
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


__all__ = ["create_cases_sync"]
