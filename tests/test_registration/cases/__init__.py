from inngest._internal import server_lib

from . import (
    base,
    cloud_branch_env,
    disallow_in_band,
    in_band_invalid_sig,
    in_band_missing_sig,
    missing_sync_kind_header,
    server_kind_mismatch,
)

_modules = (
    cloud_branch_env,
    disallow_in_band,
    in_band_invalid_sig,
    in_band_missing_sig,
    missing_sync_kind_header,
    server_kind_mismatch,
)


def create_cases(framework: server_lib.Framework) -> list[base.Case]:
    return [module.create(framework) for module in _modules]


__all__ = ["create_cases"]
