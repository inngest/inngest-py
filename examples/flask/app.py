import flask
import src.inngest

import examples.functions
import inngest.flask

app = flask.Flask(__name__)


inngest.flask.serve(
    app,
    src.inngest.inngest_client,
    examples.functions.functions_sync,
)
app.run(port=8000)
