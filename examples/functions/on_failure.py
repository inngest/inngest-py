import inngest


def _on_failure(
    **_kwargs: object,
) -> None:
    print("on_failure called")


@inngest.create_function(
    fn_id="on_failure",
    on_failure=_on_failure,
    retries=0,
    trigger=inngest.TriggerEvent(event="app/on_failure"),
)
def fn_sync(*, run_id: str, **_kwargs: object) -> None:
    raise Exception("intentional error")
