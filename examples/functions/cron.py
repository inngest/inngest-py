import os

import inngest

if os.getenv("ENABLE_CRONS") == "1":
    trigger = inngest.TriggerCron(cron="* * * * *")
else:
    trigger = inngest.TriggerEvent(event="cron")


@inngest.create_function(
    fn_id="cron",
    trigger=trigger,
)
async def fn(**_kwargs: object) -> None:
    pass


@inngest.create_function(
    fn_id="cron_sync",
    trigger=trigger,
)
def fn_sync(**_kwargs: object) -> None:
    pass
