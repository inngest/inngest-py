from inngest._internal import const, env_lib


def get_max_worker_concurrency() -> int | None:
    """
    Get the maximum number of worker concurrency from the environment.
    """
    return env_lib.get_int(const.EnvKey.CONNECT_MAX_WORKER_CONCURRENCY)
