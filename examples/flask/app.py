import flask
from src.inngest import inngest_client

import inngest.flask
from examples import functions

app = flask.Flask(__name__)


inngest.flask.serve(
    app,
    inngest_client,
    functions.create_sync_functions(inngest_client),
)
app.run(port=8000)
