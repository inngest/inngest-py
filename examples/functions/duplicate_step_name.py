import inngest


@inngest.create_function(
    fn_id="duplicate_step_name_sync",
    trigger=inngest.TriggerEvent(event="app/duplicate_step_name_sync"),
)
def fn_sync(*, step: inngest.StepSync, **_kwargs: object) -> str:
    for _ in range(3):
        step.run("foo", lambda: None)

    return "done"
