import datetime

import inngest


@inngest.create_function(
    debounce=inngest.Debounce(period=datetime.timedelta(seconds=5)),
    fn_id="debounce",
    trigger=inngest.TriggerEvent(event="app/debounce"),
)
def fn_sync(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    print(ctx.run_id)
