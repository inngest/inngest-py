import pytest

from inngest.experimental import dev_server

pytest.register_assert_rewrite("tests")


def pytest_configure(config: pytest.Config) -> None:
    dev_server.server.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    print("pytest_unconfigure")
    dev_server.server.stop()
