import inngest


def _on_failure(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> None:
    print("on_failure called")


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        fn_id="on_failure",
        on_failure=_on_failure,
        retries=0,
        trigger=inngest.TriggerEvent(event="app/on_failure"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        raise Exception("intentional error")

    return fn
