import datetime

import inngest


@inngest.create_function_sync(
    fn_id="two_steps_and_sleep",
    name="Two steps and sleep",
    trigger=inngest.TriggerEvent(event="app/two_steps_and_sleep"),
)
def fn_sync(*, step: inngest.StepSync, **_kwargs: object) -> str:
    user_id = step.run("get_user_id", lambda: 1)
    step.run("print_user_id", lambda: f"user ID is {user_id}")

    step.sleep_until(
        "zzzzz",
        (datetime.datetime.now() + datetime.timedelta(seconds=3)),
    )

    return "done"
