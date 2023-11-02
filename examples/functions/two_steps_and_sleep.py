import datetime

import inngest


@inngest.create_function(
    fn_id="two_steps_and_sleep",
    trigger=inngest.TriggerEvent(event="app/two_steps_and_sleep"),
)
async def fn(*, step: inngest.Step, **_kwargs: object) -> str:
    user_id = await step.run("get_user_id", lambda: 1)
    await step.run("print_user_id", lambda: f"user ID is {user_id}")

    await step.sleep_until(
        "zzzzz",
        (datetime.datetime.now() + datetime.timedelta(seconds=3)),
    )

    return "done"


@inngest.create_function(
    fn_id="two_steps_and_sleep_sync",
    trigger=inngest.TriggerEvent(event="app/two_steps_and_sleep_sync"),
)
def fn_sync(*, step: inngest.StepSync, **_kwargs: object) -> str:
    user_id = step.run("get_user_id", lambda: 1)
    step.run("print_user_id", lambda: f"user ID is {user_id}")

    step.sleep_until(
        "zzzzz",
        (datetime.datetime.now() + datetime.timedelta(seconds=3)),
    )

    return "done"
