from inngest._internal import server_lib

from . import (
    base,
    cloud_mode_in_band_invalid_sig,
    cloud_mode_in_band_missing_sig,
    cloud_mode_in_band_valid_sig,
    dev_mode_in_band,
    in_band_disallowed,
    missing_sync_kind,
    out_of_band,
    server_kind_mismatch,
)

_modules = (
    cloud_mode_in_band_invalid_sig,
    cloud_mode_in_band_missing_sig,
    cloud_mode_in_band_valid_sig,
    dev_mode_in_band,
    in_band_disallowed,
    missing_sync_kind,
    out_of_band,
    server_kind_mismatch,
)


def create_cases(framework: server_lib.Framework) -> list[base.Case]:
    return [module.create(framework) for module in _modules]


__all__ = ["create_cases"]
