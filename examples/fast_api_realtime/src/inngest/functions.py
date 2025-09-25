import inngest
from inngest.experimental import realtime

from .client import inngest_client


@inngest_client.create_function(
    fn_id="python-realtime-publish",
    trigger=inngest.TriggerEvent(event="realtime.test"),
)
async def python_realtime_publish(ctx: inngest.Context) -> str:
    async def my_first_step() -> dict[str, str]:
        result = {"message": "My llm response from python!"}
        await realtime.publish(
            client=inngest_client,
            channel="user:user_123456789",
            topic="messages",
            data=result,
        )
        return result

    await ctx.step.run("my-first-step", my_first_step)

    return "Finished!"
