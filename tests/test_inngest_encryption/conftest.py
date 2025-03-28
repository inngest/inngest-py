import pytest
from inngest.experimental import dev_server


def pytest_configure(config: pytest.Config) -> None:
    dev_server.server.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    dev_server.server.stop()
