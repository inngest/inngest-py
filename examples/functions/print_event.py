import inngest


@inngest.create_function(
    fn_id="print_event",
    trigger=inngest.TriggerEvent(event="app/print_event"),
)
async def fn(
    ctx: inngest.Context,
    step: inngest.Step,
) -> None:
    async def _print_data() -> dict[str, object]:
        print(ctx.event.data)
        return ctx.event.data

    await step.run("print_data", _print_data)

    async def _print_user() -> dict[str, object]:
        print(ctx.event.user)
        return ctx.event.user

    await step.run("print_user", _print_user)


@inngest.create_function(
    fn_id="print_event_sync",
    trigger=inngest.TriggerEvent(event="app/print_event_sync"),
)
def fn_sync(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    def _print_data() -> dict[str, object]:
        print(ctx.event.data)
        return ctx.event.data

    step.run("print_data", _print_data)

    def _print_user() -> dict[str, object]:
        print(ctx.event.user)
        return ctx.event.user

    step.run("print_user", _print_user)
