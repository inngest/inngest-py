import asyncio

from inngest.connect import connect
from src.inngest.client import inngest_client
from src.inngest.functions import hello

asyncio.run(connect([(inngest_client, [hello])]).start())
