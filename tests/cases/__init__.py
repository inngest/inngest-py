import inngest

from . import (
    base,
    batch_that_needs_api,
    cancel,
    change_step_error,
    client_middleware,
    client_send,
    crazy_ids,
    debounce,
    dedupe_step_ids,
    event_payload,
    function_args,
    function_middleware,
    inconsistent_step_order,
    invoke_by_id,
    invoke_by_object,
    invoke_failure,
    logger,
    multiple_triggers,
    no_cancel_if_exp_not_match,
    no_steps,
    non_retriable_error,
    on_failure,
    parallel_steps,
    sleep_until,
    tuple_output,
    two_steps,
    unexpected_step_during_targeting,
    unserializable_step_output,
    wait_for_event_fulfill,
    wait_for_event_timeout_if_exp_not_match,
    wait_for_event_timeout_name_not_match,
)

_modules = (
    batch_that_needs_api,
    cancel,
    change_step_error,
    client_middleware,
    client_send,
    crazy_ids,
    debounce,
    dedupe_step_ids,
    event_payload,
    function_args,
    function_middleware,
    inconsistent_step_order,
    invoke_by_id,
    invoke_by_object,
    invoke_failure,
    logger,
    multiple_triggers,
    no_cancel_if_exp_not_match,
    no_steps,
    non_retriable_error,
    on_failure,
    parallel_steps,
    sleep_until,
    tuple_output,
    two_steps,
    unexpected_step_during_targeting,
    unserializable_step_output,
    wait_for_event_fulfill,
    wait_for_event_timeout_if_exp_not_match,
    wait_for_event_timeout_name_not_match,
)


def create_async_cases(
    client: inngest.Inngest,
    framework: str,
) -> list[base.Case]:
    return [
        module.create(client, framework, is_sync=False) for module in _modules
    ]


def create_sync_cases(
    client: inngest.Inngest,
    framework: str,
) -> list[base.Case]:
    return [
        module.create(client, framework, is_sync=True) for module in _modules
    ]


__all__ = ["create_async_cases", "create_sync_cases"]
