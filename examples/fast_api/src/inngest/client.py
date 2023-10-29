import logging

import pythonjsonlogger.jsonlogger

import inngest

logHandler = logging.StreamHandler()
formatter = pythonjsonlogger.jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(logHandler)

inngest_client = inngest.Inngest(app_id="flask_example", logger=logger)
