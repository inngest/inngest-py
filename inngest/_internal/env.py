import os

from . import const


def is_truthy(env_var: const.EnvKey, *, default: bool = False) -> bool:
    val = os.getenv(env_var.value)
    if val is None:
        return default

    return val.lower() in ("true", "1")
