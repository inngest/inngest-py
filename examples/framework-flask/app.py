from flask import Flask
import inngest

from src.inngest import functions, inngest_client


app = Flask(__name__)

inngest.flask.serve(app, inngest_client, functions)
app.run(debug=True, port=8000)
