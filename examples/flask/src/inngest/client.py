import os

import inngest

inngest_client = inngest.Inngest(
    app_id="flask_example",
    is_production=os.getenv("ENV") == "production",
)
