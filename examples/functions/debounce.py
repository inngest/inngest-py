import datetime

import inngest


@inngest.create_function(
    inngest.FunctionOpts(
        debounce=inngest.Debounce(period=datetime.timedelta(seconds=5)),
        id="debounce",
    ),
    inngest.TriggerEvent(event="app/debounce"),
)
def fn(*, run_id: str, **_kwargs: object) -> None:
    print(run_id)
