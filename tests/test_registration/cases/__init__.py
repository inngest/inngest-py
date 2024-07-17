from inngest._internal import server_lib

from . import (
    base,
    cloud_branch_env,
    invalid_signature,
    server_kind_mismatch,
    signed,
    unsigned,
)

_modules = (
    cloud_branch_env,
    invalid_signature,
    server_kind_mismatch,
    signed,
    unsigned,
)


def create_cases(framework: server_lib.Framework) -> list[base.Case]:
    return [module.create(framework) for module in _modules]


__all__ = ["create_cases"]
