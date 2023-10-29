import time

import inngest


@inngest.create_function(
    inngest.FunctionOpts(
        cancel=[inngest.Cancel(event="app/cancel.cancel")],
        id="cancel",
    ),
    inngest.TriggerEvent(event="app/cancel"),
)
def fn(*, run_id: str, **_kwargs: object) -> None:
    time.sleep(5)
