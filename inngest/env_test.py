import os

from .env import allow_dev_server, EnvKey


def test_allow_dev_server() -> None:
    assert allow_dev_server() is True

    os.environ["CF_PAGES"] = "1"
    assert allow_dev_server() is False
    _clear()

    os.environ["CONTEXT"] = "production"
    assert allow_dev_server() is False
    _clear()

    os.environ["DENO_DEPLOYMENT_ID"] = "1"
    assert allow_dev_server() is False
    _clear()

    os.environ["ENVIRONMENT"] = "production"
    assert allow_dev_server() is False
    _clear()

    os.environ["FLASK_ENV"] = "production"
    assert allow_dev_server() is False
    _clear()

    os.environ["VERCEL_ENV"] = "production"
    assert allow_dev_server() is False
    _clear()


def _clear() -> None:
    for key in EnvKey:
        os.environ.pop(key.value, None)
