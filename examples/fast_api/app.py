import fastapi
import uvicorn
from src.inngest import inngest_client

import inngest.fast_api
from examples import functions

app = fastapi.FastAPI()


inngest.fast_api.serve(
    app,
    inngest_client,
    functions.create_async_functions(inngest_client),
)

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
