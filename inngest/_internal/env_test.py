import os

from . import env


def test_allow_dev_server() -> None:
    assert env.is_prod() is False

    os.environ["CF_PAGES"] = "1"
    assert env.is_prod() is True
    _clear()

    os.environ["CONTEXT"] = "production"
    assert env.is_prod() is True
    _clear()

    os.environ["ENVIRONMENT"] = "production"
    assert env.is_prod() is True
    _clear()

    os.environ["FLASK_ENV"] = "production"
    assert env.is_prod() is True
    _clear()

    os.environ["VERCEL_ENV"] = "production"
    assert env.is_prod() is True
    _clear()


def _clear() -> None:
    for key in env.EnvKey:
        os.environ.pop(key.value, None)
