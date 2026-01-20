import os
import random
import string


def random_suffix(value: str) -> str:
    return f"{value}-{_random_string(16)}"


def _random_string(length: int) -> str:
    return "".join(
        random.choices(string.ascii_letters + string.digits, k=length)
    )


def worker_suffix(value: str) -> str:
    """
    Suffix the app ID with the worker ID if running in a distributed test.
    Without this, running tests in multi-worker mode will cause app syncs to
    clobber each other
    """

    suffix = ""
    worker_id = os.getenv("PYTEST_XDIST_WORKER")
    if worker_id:
        suffix += f"-{worker_id}"

    return value + suffix
