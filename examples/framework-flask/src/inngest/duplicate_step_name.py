import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="duplicate-step-name", name="Duplicate step name"),
    inngest.TriggerEvent(event="app/duplicate-step-name"),
)
def fn(*, step: inngest.Step, **_: object) -> str:
    for _i in range(3):
        i = _i
        step.run("foo", lambda: i)

    return "done"
