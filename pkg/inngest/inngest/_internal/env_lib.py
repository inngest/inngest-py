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


def is_false(env_var: const.EnvKey) -> bool:
    val = os.getenv(env_var.value)
    if val is None:
        return False
    val = val.strip()

    return val.lower() in ("false", "0")


def is_true(env_var: const.EnvKey) -> bool:
    val = os.getenv(env_var.value)
    if val is None:
        return False
    val = val.strip()

    return val.lower() in ("true", "1")


def is_truthy(env_var: const.EnvKey) -> bool:
    val = os.getenv(env_var.value)
    if val is None:
        return False
    val = val.strip()

    if val.lower() in ("false", "0", ""):
        return False

    return True


def get_int(env_var: const.EnvKey) -> typing.Optional[int]:
    """
    Get an int from an env var. Returns None if the env var is not set or if its
    value is not an int.
    """

    val = os.getenv(env_var.value)
    if not isinstance(val, str):
        return None
    try:
        return int(val)
    except ValueError:
        return None


def get_streaming(env_var: const.EnvKey) -> typing.Optional[const.Streaming]:
    val = os.getenv(env_var.value)
    if val is None:
        return None
    val = val.strip().lower()

    if val == "allow":
        # Accept "allow" to improve cross-language compatibility (the TS SDK has
        # "allow"). But treat it as the same as "force".
        return const.Streaming.FORCE

    try:
        return const.Streaming(val)
    except ValueError:
        return None
