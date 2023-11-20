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


def create_cases(framework: str) -> list[base.Case]:
    cases: list[base.Case] = []
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
    ):
        cases.append(case.create(framework, is_sync=False))

    return cases


def create_cases_sync(framework: str) -> list[base.Case]:
    return [
        case.create(framework, is_sync=True)
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


__all__ = ["create_cases_sync"]
