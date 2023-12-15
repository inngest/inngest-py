import datetime

import inngest


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        fn_id="wait_for_event",
        trigger=inngest.TriggerEvent(event="app/wait_for_event"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        res = step.wait_for_event(
            "wait",
            event="app/wait_for_event.fulfill",
            timeout=datetime.timedelta(seconds=2),
        )
        step.run("print-result", lambda: print(res))

    return fn
