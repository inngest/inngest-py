import logging
import os

import pythonjsonlogger.jsonlogger

import inngest

logHandler = logging.StreamHandler()
formatter = pythonjsonlogger.jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(logHandler)

inngest_client = inngest.Inngest(
    app_id="fast_api_example",
    logger=logger,
    is_production=os.getenv("ENV") == "production",
)
