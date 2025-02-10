import inngest.flask
from src.flask import app
from src.inngest.client import inngest_client
from src.inngest.functions import hello

inngest.flask.serve(
    app,
    inngest_client,
    [hello],
)

app.run(port=8000)
