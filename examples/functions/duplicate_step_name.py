import inngest


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        fn_id="duplicate_step_name_sync",
        trigger=inngest.TriggerEvent(event="app/duplicate_step_name_sync"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> str:
        for _ in range(3):
            step.run("foo", lambda: None)

        return "done"

    return fn
