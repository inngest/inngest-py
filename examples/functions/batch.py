import inngest


@inngest.create_function(
    inngest.FunctionOpts(
        batch_events=inngest.BatchConfig(max_size=2, timeout="60s"),
        id="batch",
        name="Batch",
    ),
    inngest.TriggerEvent(event="app/batch"),
)
def fn(
    *,
    events: list[inngest.Event],
    step: inngest.Step,
    **_kwargs: object,
) -> None:
    def _print_events() -> None:
        print(len(events))

    step.run("print_events", _print_events)
