import os
from inngest._internal import const

def get_max_worker_concurrency() -> int | None:
    """
    Get the maximum number of worker concurrency from the environment.
    """
    res = os.getenv(const.EnvKey.CONNECT_MAX_WORKER_CONCURRENCY.value)
    if res is None or res == "":
        return None
    return int(res)
