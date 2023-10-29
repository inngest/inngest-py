import datetime

import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="wait_for_event", name="wait_for_event"),
    inngest.TriggerEvent(event="app/wait_for_event"),
)
def fn(*, step: inngest.Step, **_kwargs: object) -> None:
    res = step.wait_for_event(
        "wait",
        event="app/wait_for_event.fulfill",
        timeout=datetime.timedelta(seconds=2),
    )
    step.run("print-result", lambda: print(res))
