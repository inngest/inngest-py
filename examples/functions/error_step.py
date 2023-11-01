import inngest


class MyError(Exception):
    pass


@inngest.create_function(
    fn_id="error_step",
    retries=0,
    trigger=inngest.TriggerEvent(event="app/error_step"),
)
def fn_sync(*, step: inngest.StepSync, **_kwargs: object) -> None:
    step.run("first_step", lambda: None)

    def _second_step() -> None:
        raise MyError("oh no")

    step.run("second_step", _second_step)
