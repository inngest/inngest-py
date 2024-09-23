import os
import typing

import inngest._internal.const as const


def get_serve_origin(code_value: typing.Optional[str]) -> typing.Optional[str]:
    if code_value is not None:
        return code_value

    env_var_value = os.getenv(const.EnvKey.SERVE_ORIGIN.value)
    if env_var_value:
        return env_var_value

    return None


def get_serve_path(code_value: typing.Optional[str]) -> typing.Optional[str]:
    if code_value is not None:
        return code_value

    env_var_value = os.getenv(const.EnvKey.SERVE_PATH.value)
    if env_var_value:
        return env_var_value

    return None
