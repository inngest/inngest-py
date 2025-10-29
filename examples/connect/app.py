import asyncio

from inngest.connect import connect
from src.inngest.client import inngest_client, inngest_client_slow
from src.inngest.functions import hello, hello_slow, hello_really_slow

# generic example
asyncio.run(connect([(inngest_client, [hello])], max_worker_concurrency=1).start())

# slow example with worker concurrency limit
asyncio.run(
    connect(
        [(inngest_client_slow, [hello_slow, hello_really_slow])],
        max_worker_concurrency=1
    ).start())
