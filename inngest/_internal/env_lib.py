import os
import typing

from . import const


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


def is_true(env_var: const.EnvKey) -> bool:
    val = os.getenv(env_var.value)
    if val is None:
        return False

    if val.lower() in ("true", "1"):
        return True

    return False
