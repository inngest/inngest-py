import inngest


@inngest.create_function(
    fn_id="no_steps",
    trigger=inngest.TriggerEvent(event="app/no_steps"),
)
def fn_sync(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> int:
    return 1
