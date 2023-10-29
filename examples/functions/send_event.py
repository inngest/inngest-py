import inngest


@inngest.create_function_sync(
    fn_id="send_event",
    name="Send event",
    trigger=inngest.TriggerEvent(event="app/send_event"),
)
def fn_sync(*, step: inngest.StepSync, **_kwargs: object) -> None:
    step.run("first", lambda: None)
    step.send_event("send", inngest.Event(name="foo"))
    step.run("second", lambda: None)
