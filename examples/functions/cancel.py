import time

import inngest


@inngest.create_function(
    cancel=[inngest.Cancel(event="app/cancel.cancel")],
    fn_id="cancel",
    trigger=inngest.TriggerEvent(event="app/cancel"),
)
def fn_sync(*, run_id: str, **_kwargs: object) -> None:
    time.sleep(5)
