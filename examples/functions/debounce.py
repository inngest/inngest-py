import datetime

import inngest


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        debounce=inngest.Debounce(period=datetime.timedelta(seconds=5)),
        fn_id="debounce",
        trigger=inngest.TriggerEvent(event="app/debounce"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        print(ctx.run_id)

    return fn
