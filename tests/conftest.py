from pytest import Config

from . import dev_server


def pytest_configure(config: Config) -> None:
    dev_server.singleton.start()


def pytest_unconfigure(config: Config) -> None:
    dev_server.singleton.stop()
