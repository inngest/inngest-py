import logging

from flask import Flask
from src.inngest import inngest_client
from pythonjsonlogger import jsonlogger
from examples.functions import functions
import inngest


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
