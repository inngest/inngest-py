import inngest


@inngest.create_function(
    fn_id="no_steps",
    trigger=inngest.TriggerEvent(event="app/no_steps"),
)
def fn_sync(**_kwargs: object) -> int:
    return 1
