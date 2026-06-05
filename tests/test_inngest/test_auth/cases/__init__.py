from inngest._internal import server_lib

from . import (
    base,
    cloud_invalid_auth,
    cloud_missing_auth,
    cloud_unsupported_method,
    cloud_valid_auth,
    dev_missing_auth,
)

_modules = (
    cloud_valid_auth,
    cloud_invalid_auth,
    cloud_missing_auth,
    cloud_unsupported_method,
    dev_missing_auth,
)


def create_cases(framework: server_lib.Framework) -> list[base.Case]:
    return [
        case for module in _modules for case in module.create_cases(framework)
    ]


__all__ = ["create_cases"]
