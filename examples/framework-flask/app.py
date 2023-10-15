from flask import Flask
import inngest

from src.client import inngest_client
from src.functions import functions


app = Flask(__name__)

inngest.flask.serve(app, inngest_client, functions)
app.run(debug=True, port=8000)
