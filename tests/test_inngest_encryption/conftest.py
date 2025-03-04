import pytest
from inngest.experimental import dev_server

# Makes `assert` calls display a useful diff when they fail. Without this,
# `assert` failures just show "AssertionError" with no helpful diff.
pytest.register_assert_rewrite("test_inngest_encryption")


def pytest_configure(config: pytest.Config) -> None:
    dev_server.server.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    dev_server.server.stop()
