import os
import tempfile

import pytest
from inngest.experimental import dev_server


def pytest_configure(config: pytest.Config) -> None:
    # Start the Dev Server logged out of Inngest Cloud, even if the developer
    # ran `inngest login`. Otherwise it proxies sandboxes to Cloud for real.
    os.environ["INNGEST_CONFIG_DIR"] = tempfile.mkdtemp()
    dev_server.server.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    dev_server.server.stop()
