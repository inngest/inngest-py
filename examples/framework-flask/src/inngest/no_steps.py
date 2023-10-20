import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="no-steps", name="No steps"),
    inngest.TriggerEvent(event="app/no-steps"),
)
def fn(*, event: inngest.Event, step: inngest.Step) -> int:
    return 1
