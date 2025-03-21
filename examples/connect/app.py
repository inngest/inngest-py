import asyncio

import inngest.experimental.connect
from src.inngest.client import inngest_client
from src.inngest.functions import hello

asyncio.run(
    inngest.experimental.connect.connect(
        [(inngest_client, [hello])],
    ).start()
)
