import logging

import inngest
from src.flask import app

logger = logging.getLogger(f"{app.logger.name}.inngest")
logger.setLevel(logging.DEBUG)

inngest_client = inngest.Inngest(app_id="flask_example", logger=logger)
