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
    *,
    events: list[inngest.Event],
    step: inngest.StepSync,
    **_kwargs: object,
) -> None:
    def _print_events() -> None:
        print(len(events))

    step.run("print_events", _print_events)
