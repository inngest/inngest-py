import logging

import flask
import pythonjsonlogger.jsonlogger
import src.inngest

import examples.functions
import inngest.flask

app = flask.Flask(__name__)

# Set up logging.
logHandler = logging.StreamHandler()
formatter = pythonjsonlogger.jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
app.logger.addHandler(logHandler)


inngest.flask.serve(
    app,
    src.inngest.inngest_client,
    examples.functions.functions,
)
app.run(port=8000)
