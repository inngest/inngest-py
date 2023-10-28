import os

from .env import EnvKey, is_prod


def test_allow_dev_server() -> None:
    assert is_prod() is False

    os.environ["CF_PAGES"] = "1"
    assert is_prod() is True
    _clear()

    os.environ["CONTEXT"] = "production"
    assert is_prod() is True
    _clear()

    os.environ["ENVIRONMENT"] = "production"
    assert is_prod() is True
    _clear()

    os.environ["FLASK_ENV"] = "production"
    assert is_prod() is True
    _clear()

    os.environ["VERCEL_ENV"] = "production"
    assert is_prod() is True
    _clear()


def _clear() -> None:
    for key in EnvKey:
        os.environ.pop(key.value, None)
