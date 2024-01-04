import pytest

from . import dev_server

pytest.register_assert_rewrite("tests")


def pytest_configure(config: pytest.Config) -> None:
    dev_server.singleton.start()


def pytest_unconfigure(config: pytest.Config) -> None:
    dev_server.singleton.stop()
