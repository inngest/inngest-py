import inngest

from .client import inngest_client_slow


@inngest_client_slow.create_function(
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
