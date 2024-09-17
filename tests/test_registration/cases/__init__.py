from inngest._internal import server_lib

from . import (
    base,
    cloud_branch_env,
    in_sync_invalid_sig,
    in_sync_missing_sig,
    out_of_band,
    server_kind_mismatch,
)

_modules = (
    cloud_branch_env,
    in_sync_invalid_sig,
    in_sync_missing_sig,
    out_of_band,
    server_kind_mismatch,
)


def create_cases(framework: server_lib.Framework) -> list[base.Case]:
    return [module.create(framework) for module in _modules]


__all__ = ["create_cases"]
