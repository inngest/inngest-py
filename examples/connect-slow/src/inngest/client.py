import inngest
import structlog

logger = structlog.get_logger()

inngest_client_slow = inngest.Inngest(app_id="connect_example_slow", logger=logger)
