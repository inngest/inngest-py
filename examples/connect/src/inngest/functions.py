import inngest

from .client import inngest_client


@inngest_client.create_function(
    fn_id="hello-world",
    trigger=inngest.TriggerEvent(event="say-hello"),
)
async def hello(ctx: inngest.Context) -> str:
    return "Hello world!"


async def get_message(name: str) -> str:
    return f"Hello {name}!"


@inngest_client.create_function(
    fn_id="fn-1",
    trigger=inngest.TriggerEvent(event="event-1"),
)
async def fn_1(ctx: inngest.Context) -> str:
    msg = await ctx.step.run("get-message", get_message, "Alice")
    return msg
