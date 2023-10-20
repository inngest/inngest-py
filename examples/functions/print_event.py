import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="print_event", name="Print event"),
    inngest.TriggerEvent(event="app/print_event"),
)
def fn(*, event: inngest.Event, step: inngest.Step, **_kwargs: object) -> None:
    def _print_data() -> dict:
        print(event.data)
        return event.data

    step.run("print_data", _print_data)

    def _print_user() -> dict:
        print(event.user)
        return event.user

    step.run("print_user", _print_user)
