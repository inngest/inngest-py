import os

import inngest

trigger: inngest.TriggerCron | inngest.TriggerEvent
if os.getenv("ENABLE_CRONS") == "1":
    trigger = inngest.TriggerCron(cron="* * * * *")
else:
    trigger = inngest.TriggerEvent(event="cron")


@inngest.create_function(
    fn_id="cron",
    trigger=trigger,
)
async def fn(
    ctx: inngest.Context,
    step: inngest.Step,
) -> None:
    pass


@inngest.create_function(
    fn_id="cron_sync",
    trigger=trigger,
)
def fn_sync(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    pass
