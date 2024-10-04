import inngest

from .inngest_client import inngest_client


@inngest_client.create_function(
    fn_id="hello-world",
    trigger=inngest.TriggerEvent(event="say-hello"),
)
def hello(
    ctx: inngest.Context,
    step: inngest.StepSync,
) -> str:
    return "Hello world!"
