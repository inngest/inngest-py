import inngest


class MyError(Exception):
    pass


@inngest.create_function(
    inngest.FunctionOpts(id="error_step", name="Error step", retries=0),
    inngest.TriggerEvent(event="app/error_step"),
)
def fn(*, step: inngest.Step, **_kwargs: object) -> None:
    step.run("first_step", lambda: None)

    def _second_step() -> None:
        raise MyError("oh no")

    step.run("second_step", _second_step)
