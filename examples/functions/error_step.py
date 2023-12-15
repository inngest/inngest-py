import inngest


class MyError(Exception):
    pass


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        fn_id="error_step",
        retries=0,
        trigger=inngest.TriggerEvent(event="app/error_step"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> None:
        step.run("first_step", lambda: None)

        def _second_step() -> None:
            raise MyError("oh no")

        step.run("second_step", _second_step)

    return fn
