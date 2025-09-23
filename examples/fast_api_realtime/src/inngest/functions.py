import inngest

from .client import inngest_client


@inngest_client.create_function(
    fn_id="python-realtime-publish",
    trigger=inngest.TriggerEvent(event="realtime.test"),
)
async def hello(ctx: inngest.Context) -> str:
    async def my_first_step() -> dict[str, str]:
        return {"message": "My llm response from python!"}

    result = await ctx.step.run("my-first-step", my_first_step)

    await ctx.experimental.publish("user:user_123456789", "messages", result)

    return "Hello world!"
