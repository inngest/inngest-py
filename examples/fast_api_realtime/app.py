import fastapi
import inngest.fast_api
from fastapi.staticfiles import StaticFiles
from src.inngest.client import inngest_client
from src.inngest.functions import hello

app = fastapi.FastAPI()


inngest.fast_api.serve(
    app,
    inngest_client,
    [hello],
)


@app.get("/api/get_subscription_token")
async def get_realtime_token():
    # Here, you can get params from the request to;
    # - Authorize what the user is allowed to subscribe to
    # - Allow the client to specify what topics they want to subscribe to
    return await inngest_client.experimental.get_subscription_token(
        "user:user_123456789", ["messages"]
    )


@app.get("/api/trigger_function")
async def trigger_function():
    return await inngest_client.send(
        [
            inngest.Event(
                name="realtime.test",
                data={
                    "message": "Hello, world!",
                    "userId": "user_123456789",
                },
            )
        ]
    )


@app.get("/", response_class=fastapi.responses.HTMLResponse)
def root():
    with open("dist/index.html") as f:
        return fastapi.responses.HTMLResponse(content=f.read())


app.mount("/", StaticFiles(directory="dist"), name="static")
