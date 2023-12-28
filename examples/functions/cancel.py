import time

import inngest


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        cancel=[inngest.Cancel(event="app/cancel.cancel")],
        fn_id="cancel",
        trigger=inngest.TriggerEvent(event="app/cancel"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        time.sleep(5)

    return fn
