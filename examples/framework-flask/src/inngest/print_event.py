import inngest


@inngest.create_function(
    inngest.FunctionOpts(id="print-event", name="Print event"),
    inngest.TriggerEvent(event="app/print-event"),
)
def fn(*, event: inngest.Event, step: inngest.Step, **_: object) -> None:
    def _print_data() -> dict:
        print(event.data)
        return event.data

    step.run("print-data", _print_data)

    def _print_user() -> dict:
        print(event.user)
        return event.user

    step.run("print-user", _print_user)
