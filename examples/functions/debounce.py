import datetime

import inngest


@inngest.create_function(
    debounce=inngest.Debounce(period=datetime.timedelta(seconds=5)),
    fn_id="debounce",
    trigger=inngest.TriggerEvent(event="app/debounce"),
)
def fn_sync(*, run_id: str, **_kwargs: object) -> None:
    print(run_id)
