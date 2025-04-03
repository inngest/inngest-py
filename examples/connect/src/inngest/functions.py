import inngest

from .client import inngest_client


@inngest_client.create_function(
    fn_id="hello-world",
    trigger=inngest.TriggerEvent(event="say-hello"),
)
async def hello(ctx: inngest.Context) -> None:
    await ctx.group.parallel(
        (
            lambda: ctx.step.run("step-1", lambda: "do stuff"),
            lambda: ctx.step.run("step-2", lambda: "do other stuff"),
        )
    )
