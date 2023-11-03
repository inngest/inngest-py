import logging

import flask
import src.inngest

import examples.functions
import inngest.flask

app = flask.Flask(__name__)


log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)


inngest.flask.serve(
    app,
    src.inngest.inngest_client,
    examples.functions.functions_sync,
)
app.run(port=8000)
