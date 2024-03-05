import os

from . import const


def is_true(env_var: const.EnvKey) -> bool:
    val = os.getenv(env_var.value)
    if val is None:
        return False

    if val.lower() in ("true", "1"):
        return True

    return False
