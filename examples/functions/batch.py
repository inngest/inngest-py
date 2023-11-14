import datetime

import inngest


@inngest.create_function(
    batch_events=inngest.Batch(
        max_size=2,
        timeout=datetime.timedelta(minutes=1),
    ),
    fn_id="batch",
    trigger=inngest.TriggerEvent(event="app/batch"),
)
def fn_sync(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    def _print_events() -> None:
        print(len(ctx.events))

    step.run("print_events", _print_events)
