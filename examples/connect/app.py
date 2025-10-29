import asyncio

from inngest.connect import connect
from src.inngest.client import inngest_client
from src.inngest.functions import hello

# generic example
asyncio.run(connect([(inngest_client, [hello])], max_worker_concurrency=1).start())
