import inngest


@inngest.create_function(
    fn_id="print_event",
    trigger=inngest.TriggerEvent(event="app/print_event"),
)
def fn_sync(
    *, event: inngest.Event, step: inngest.StepSync, **_kwargs: object
) -> None:
    def _print_data() -> dict[str, object]:
        print(event.data)
        return event.data

    step.run("print_data", _print_data)

    def _print_user() -> dict[str, object]:
        print(event.user)
        return event.user

    step.run("print_user", _print_user)


@inngest.create_function(
    fn_id="print_event_async",
    trigger=inngest.TriggerEvent(event="app/print_event_async"),
)
async def fn(
    *, event: inngest.Event, step: inngest.Step, **_kwargs: object
) -> None:
    async def _print_data() -> dict[str, object]:
        print(event.data)
        return event.data

    await step.run("print_data", _print_data)

    async def _print_user() -> dict[str, object]:
        print(event.user)
        return event.user

    await step.run("print_user", _print_user)
