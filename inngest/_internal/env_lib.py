import os
import typing

from . import const, net, server_lib


def get_environment_name() -> typing.Optional[str]:
    """
    Get the Inngest environment name from env vars. Checks our env var and cloud
    platform (e.g. Vercel) specific env vars
    """

    return (
        os.getenv(const.EnvKey.ENV.value)
        or os.getenv(const.EnvKey.RAILWAY_GIT_BRANCH.value)
        or os.getenv(const.EnvKey.RENDER_GIT_BRANCH.value)
        or os.getenv(const.EnvKey.VERCEL_GIT_BRANCH.value)
    )


def get_url(
    env_var: const.EnvKey,
    mode: server_lib.ServerKind,
) -> typing.Optional[str]:
    """
    Get a URL from an env var. Returns None if the env var is not set or if its value is not a valid URL
    """

    val = os.getenv(env_var.value)
    if val is None:
        return None
    val = val.strip()

    parsed = net.parse_url(val, mode)
    if isinstance(parsed, Exception):
        return None

    return parsed


def is_truthy(env_var: const.EnvKey) -> bool:
    val = os.getenv(env_var.value)
    if val is None:
        return False
    val = val.strip()

    if val.lower() in ("false", "0", ""):
        return False

    return True
