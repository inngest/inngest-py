import logging

import inngest
from inngest.experimental.encryption_middleware import EncryptionMiddleware

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.DEBUG)

inngest_client = inngest.Inngest(
    app_id="flask_example",
    logger=logger,
    middleware=[EncryptionMiddleware.factory("your-encryption-key")],
)
