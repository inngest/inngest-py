import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="no_steps", name="No steps"),
    inngest.TriggerEvent(event="app/no_steps"),
)
def fn(**_kwargs: object) -> int:
    return 1
