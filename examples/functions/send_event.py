import inngest


@inngest.create_function(
    fn_id="send_event",
    trigger=inngest.TriggerEvent(event="app/send_event"),
)
def fn_sync(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    step.run("first", lambda: None)
    step.send_event("send", inngest.Event(name="foo"))
    step.run("second", lambda: None)
