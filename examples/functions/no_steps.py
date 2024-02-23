import inngest


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        fn_id="no_steps",
        trigger=inngest.TriggerEvent(event="app/no_steps"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> int:
        raise inngest.NonRetriableError("no")
        return 1

    return fn
