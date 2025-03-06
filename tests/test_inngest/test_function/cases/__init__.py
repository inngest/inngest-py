import inngest
from inngest._internal import server_lib

from . import (
    asyncio_first_completed,
    asyncio_gather,
    asyncio_immediate_execution,
    batch_that_needs_api,
    cancel,
    change_step_error,
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
    invoke_timeout,
    logger,
    middleware_order,
    middleware_parallel_steps,
    multiple_triggers,
    no_cancel_if_exp_not_match,
    no_steps,
    non_retriable_error,
    on_failure,
    parallel_group_of_sequential_steps,
    parallel_step_disappears,
    parallel_steps,
    parallel_steps_legacy,
    pydantic_event,
    pydantic_output,
    retry_after_error,
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
    asyncio_gather,
    asyncio_first_completed,
    asyncio_immediate_execution,
    batch_that_needs_api,
    cancel,
    change_step_error,
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
    invoke_timeout,
    logger,
    middleware_order,
    middleware_parallel_steps,
    multiple_triggers,
    no_cancel_if_exp_not_match,
    no_steps,
    non_retriable_error,
    on_failure,
    parallel_group_of_sequential_steps,
    parallel_step_disappears,
    parallel_steps,
    parallel_steps_legacy,
    pydantic_event,
    pydantic_output,
    retry_after_error,
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
