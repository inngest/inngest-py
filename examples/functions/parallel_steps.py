import asyncio
import time

import inngest


def create_async_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        fn_id="parallel_steps",
        trigger=inngest.TriggerEvent(event="app/parallel_steps"),
    )
    async def fn(
        ctx: inngest.Context,
        step: inngest.Step,
    ) -> tuple[int, ...]:
        async def _step_1a() -> int:
            await asyncio.sleep(2)
            return 1

        async def _step_1b() -> int:
            await asyncio.sleep(2)
            return 2

        return await ctx.group.parallel(
            (
                lambda: step.run("1a", _step_1a),
                lambda: step.run("1b", _step_1b),
            )
        )

    return fn


def create_sync_function(client: inngest.Inngest) -> inngest.Function:
    @client.create_function(
        fn_id="parallel_steps",
        trigger=inngest.TriggerEvent(event="app/parallel_steps"),
    )
    def fn(
        ctx: inngest.Context,
        step: inngest.StepSync,
    ) -> tuple[int, ...]:
        def _step_1a() -> int:
            time.sleep(2)
            return 1

        def _step_1b() -> int:
            time.sleep(2)
            return 2

        return ctx.group.parallel_sync(
            (
                lambda: step.run("1a", _step_1a),
                lambda: step.run("1b", _step_1b),
            )
        )

    return fn
