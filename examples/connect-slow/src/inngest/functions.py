import asyncio

import inngest

from .client import inngest_client_slow

@inngest_client_slow.create_function(
    fn_id="hello-world",
    trigger=inngest.TriggerEvent(event="say-hello"),
)
async def hello(ctx: inngest.Context) -> str:
    await asyncio.sleep(1)
    return "Hello World!"

@inngest_client_slow.create_function(
    fn_id="hello-slowish-world",
    trigger=inngest.TriggerEvent(event="say-hello-slowish"),
)
async def hello_slowish(ctx: inngest.Context) -> str:
    await asyncio.sleep(10)
    return "Hello Slowish World!"

@inngest_client_slow.create_function(
    fn_id="hello-slow-world",
    trigger=inngest.TriggerEvent(event="say-hello-slow"),
)
async def hello_slow(ctx: inngest.Context) -> str:
    await asyncio.sleep(100)
    return "Hello Slow World!"


@inngest_client_slow.create_function(
    fn_id="hello-really-slow-world",
    trigger=inngest.TriggerEvent(event="say-hello-really-slow"),
)
async def hello_really_slow(ctx: inngest.Context) -> str:
    await asyncio.sleep(10000)
    return "Hello Really Slow World!"
