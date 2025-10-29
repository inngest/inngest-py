import inngest

from .client import inngest_client

@inngest_client.create_function(
    fn_id="hello-world",
    trigger=inngest.TriggerEvent(event="say-hello"),
)
async def hello(ctx: inngest.Context) -> str:
    return "Hello world!"
