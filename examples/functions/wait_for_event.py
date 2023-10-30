import datetime

import inngest


@inngest.create_function_sync(
    fn_id="wait_for_event",
    name="wait_for_event",
    trigger=inngest.TriggerEvent(event="app/wait_for_event"),
)
def fn_sync(*, step: inngest.StepSync, **_kwargs: object) -> None:
    res = step.wait_for_event(
        "wait",
        event="app/wait_for_event.fulfill",
        timeout=datetime.timedelta(seconds=2),
    )
    step.run("print-result", lambda: print(res))
