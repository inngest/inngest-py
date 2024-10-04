import fastapi
from src.inngest.client import inngest_client
from src.inngest.functions import hello

import inngest.fast_api

app = fastapi.FastAPI()


inngest.fast_api.serve(
    app,
    inngest_client,
    [hello],
)
