import inngest


def _on_failure(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    print("on_failure called")


@inngest.create_function(
    fn_id="on_failure",
    on_failure=_on_failure,
    retries=0,
    trigger=inngest.TriggerEvent(event="app/on_failure"),
)
def fn_sync(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    raise Exception("intentional error")
