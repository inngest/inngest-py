import fastapi
from src.inngest import inngest_client

import inngest.fast_api
from examples import functions

app = fastapi.FastAPI()


inngest.fast_api.serve(
    app,
    inngest_client,
    functions.create_async_functions(inngest_client),
)
