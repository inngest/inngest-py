import inngest

from . import (
    base,
    cancel,
    client_middleware,
    client_send,
    debounce,
    event_payload,
    function_args,
    function_middleware,
    inconsistent_step_order,
    logger,
    no_steps,
    non_retriable_error,
    on_failure,
    parallel_steps,
    sleep_until,
    two_steps,
    unserializable_step_output,
    wait_for_event_fulfill,
    wait_for_event_timeout,
)


def create_async_cases(
    client: inngest.Inngest,
    framework: str,
) -> list[base.Case]:
    return [
        case.create(client, framework, is_sync=False)
        for case in (
            cancel,
            client_middleware,
            client_send,
            debounce,
            event_payload,
            function_args,
            function_middleware,
            inconsistent_step_order,
            logger,
            no_steps,
            non_retriable_error,
            on_failure,
            parallel_steps,
            sleep_until,
            two_steps,
            unserializable_step_output,
            wait_for_event_fulfill,
            wait_for_event_timeout,
        )
    ]


def create_sync_cases(
    client: inngest.Inngest,
    framework: str,
) -> list[base.Case]:
    return [
        case.create(client, framework, is_sync=True)
        for case in (
            cancel,
            client_middleware,
            client_send,
            debounce,
            event_payload,
            function_args,
            function_middleware,
            inconsistent_step_order,
            logger,
            no_steps,
            non_retriable_error,
            on_failure,
            parallel_steps,
            sleep_until,
            two_steps,
            unserializable_step_output,
            wait_for_event_fulfill,
            wait_for_event_timeout,
        )
    ]


__all__ = ["create_async_cases", "create_sync_cases"]
