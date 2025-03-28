import inngest
import structlog

logger = structlog.get_logger()

inngest_client = inngest.Inngest(app_id="fast_api_example", logger=logger)
