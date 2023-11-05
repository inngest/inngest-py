import os

import inngest

inngest_client = inngest.Inngest(
    app_id="fast_api_example",
    is_production=os.getenv("ENV") == "production",
)
