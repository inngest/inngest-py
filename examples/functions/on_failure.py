import inngest


def _on_failure(
    attempt: int,
    event: inngest.Event,
    events: list[inngest.Event],
    run_id: str,
    step: inngest.Step,
) -> None:
    print("on_failure called")


@inngest.create_function(
    inngest.FunctionOpts(id="on_failure", on_failure=_on_failure, retries=0),
    inngest.TriggerEvent(event="app/on_failure"),
)
def fn(*, run_id: str, **_kwargs: object) -> None:
    raise Exception("intentional error")
