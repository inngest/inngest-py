import inngest
from inngest._internal import server_lib

from . import (
    async_fn_with_sync_step_callback,
    batch_that_needs_api,
    cancel,
    change_step_error,
    client_send,
    concurrent_sync_functions,
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
    invoke_timeout,
    logger,
    middleware_order,
    middleware_parallel_steps,
    multiple_triggers,
    nested_step_run,
    no_cancel_if_exp_not_match,
    no_steps,
    non_retriable_error,
    on_failure,
    parallel_group_of_sequential_steps,
    parallel_step_disappears,
    parallel_steps,
    pydantic_event,
    retry_after_error,
    singleton,
    sleep_until,
    step_callback_args,
    step_callback_kwargs,
    steps_that_needs_api,
    tuple_output,
    two_steps,
    unexpected_step_during_targeting,
    unserializable_step_output,
    wait_for_event_fulfill,
    wait_for_event_timeout_if_exp_not_match,
    wait_for_event_timeout_name_not_match,
)
from .base import Case

_modules = (
    async_fn_with_sync_step_callback,
    batch_that_needs_api,
    cancel,
    change_step_error,
    client_send,
    concurrent_sync_functions,
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
    invoke_timeout,
    logger,
    middleware_order,
    middleware_parallel_steps,
    multiple_triggers,
    nested_step_run,
    no_cancel_if_exp_not_match,
    no_steps,
    non_retriable_error,
    on_failure,
    parallel_group_of_sequential_steps,
    parallel_step_disappears,
    parallel_steps,
    pydantic_event,
    retry_after_error,
    singleton,
    sleep_until,
    step_callback_args,
    step_callback_kwargs,
    steps_that_needs_api,
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
    framework: server_lib.Framework,
) -> list[Case]:
    return [
        module.create(client, framework, is_sync=False) for module in _modules
    ]


def create_sync_cases(
    client: inngest.Inngest,
    framework: server_lib.Framework,
) -> list[Case]:
    cases = []
    for module in _modules:
        case = module.create(client, framework, is_sync=True)
        if isinstance(case.fn, list) and len(case.fn) == 0:
            continue
        cases.append(case)

    return cases
