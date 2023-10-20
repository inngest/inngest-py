import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="send_event", name="Send event"),
    inngest.TriggerEvent(event="app/send_event"),
)
def fn(*, step: inngest.Step, **_kwargs: object) -> None:
    step.run("first", lambda: None)
    step.send_event("send", inngest.Event(name="foo"))
    step.run("second", lambda: None)
