import asyncio

from inngest.connect import connect
from src.inngest.client import inngest_client_slow
from src.inngest.functions import hello_slow, hello_really_slow

# slow example with worker concurrency limit
asyncio.run(
    connect(
        [(inngest_client_slow, [hello_slow, hello_really_slow])],
        max_worker_concurrency=1
    ).start())
