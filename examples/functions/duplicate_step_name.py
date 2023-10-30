import inngest


@inngest.create_function_sync(
    fn_id="duplicate_step_name",
    name="Duplicate step name",
    trigger=inngest.TriggerEvent(event="app/duplicate_step_name"),
)
def fn_sync(*, step: inngest.StepSync, **_kwargs: object) -> str:
    for _ in range(3):
        step.run("foo", lambda: None)

    return "done"
