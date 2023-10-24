import logging

from flask import Flask
from pythonjsonlogger import jsonlogger
from src.inngest import inngest_client

import inngest
from examples.functions import functions

app = Flask(__name__)

# Set up logging.
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
app.logger.addHandler(logHandler)


inngest.flask.serve(
    app,
    inngest_client,
    functions,
)
app.run(port=8000)
