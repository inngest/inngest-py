import fastapi
import src.inngest
import uvicorn

import examples.functions
import inngest.fast_api

app = fastapi.FastAPI()


inngest.fast_api.serve(
    app,
    src.inngest.inngest_client,
    examples.functions.functions,
)

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
