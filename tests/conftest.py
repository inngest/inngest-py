from pytest import Config
from .dev_server import dev_server


def pytest_configure(config: Config) -> None:
    print("Starting Dev Server...")
    dev_server.start()


def pytest_unconfigure(config: Config) -> None:
    print("Shutting down Dev Server..")
    dev_server.stop()
