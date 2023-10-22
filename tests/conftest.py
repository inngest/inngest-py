from pytest import Config

from .dev_server import dev_server


def pytest_configure(config: Config) -> None:
    # dev_server.start()
    return None


def pytest_unconfigure(config: Config) -> None:
    # dev_server.stop()
    return None
