import inngest

from .client import inngest_client


@inngest_client.create_function(
    fn_id="hello-world",
    trigger=inngest.TriggerEvent(event="say-hello"),
)
async def hello(ctx: inngest.Context) -> str:
    return "Hello world!"


@inngest_client.create_function(
    fn_id="hello-slow-world",
    trigger=inngest.TriggerEvent(event="say-hello-slow"),
)
async def hello_slow(ctx: inngest.Context) -> str:
    time.sleep(100)
    return "Hello Slow World!"

@inngest_client_slow.create_function(
    fn_id="hello-really-slow-world",
    trigger=inngest.TriggerEvent(event="say-hello-really-slow"),
)
async def hello_really_slow(ctx: inngest.Context) -> str:
    time.sleep(10000)
    return "Hello Really Slow World!"
