import fastapi
import inngest.fast_api
from src.inngest.client import inngest_client
from src.inngest.functions import hello

app = fastapi.FastAPI()


inngest.fast_api.serve(
    app,
    inngest_client,
    [hello],
)
