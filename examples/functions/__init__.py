import inngest

from . import (
    batch,
    cancel,
    cron,
    debounce,
    duplicate_step_name,
    error_step,
    no_steps,
    on_failure,
    parallel_steps,
    print_event,
    send_event,
    two_steps_and_sleep,
    wait_for_event,
)


def create_async_functions(client: inngest.Inngest) -> list[inngest.Function]:
    return [
        cron.create_async_function(client),
        parallel_steps.create_async_function(client),
        print_event.create_async_function(client),
        two_steps_and_sleep.create_async_function(client),
    ]


def create_sync_functions(client: inngest.Inngest) -> list[inngest.Function]:
    return [
        batch.create_sync_function(client),
        cancel.create_sync_function(client),
        cron.create_sync_function(client),
        debounce.create_sync_function(client),
        duplicate_step_name.create_sync_function(client),
        error_step.create_sync_function(client),
        no_steps.create_sync_function(client),
        on_failure.create_sync_function(client),
        parallel_steps.create_sync_function(client),
        print_event.create_sync_function(client),
        send_event.create_sync_function(client),
        two_steps_and_sleep.create_sync_function(client),
        wait_for_event.create_sync_function(client),
    ]


__all__ = ["create_async_functions", "create_sync_functions"]
