import inngest


class MyError(Exception):
    pass


@inngest.create_function(
    inngest.FunctionOpts(id="error-step", name="Error step", retries=0),
    inngest.TriggerEvent(event="app/error-step"),
)
def error_step(*, event: inngest.Event, step: inngest.Step) -> None:
    def _first_step() -> None:
        pass

    step.run("first-step", _first_step)

    def _second_step() -> None:
        raise MyError("oh no")

    step.run("second-step", _second_step)
