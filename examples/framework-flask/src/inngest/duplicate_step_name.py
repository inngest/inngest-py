import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="duplicate_step_name", name="Duplicate step name"),
    inngest.TriggerEvent(event="app/duplicate_step_name"),
)
def fn(*, step: inngest.Step, **_kwargs: object) -> str:
    for _ in range(3):
        step.run("foo", lambda: None)

    return "done"
