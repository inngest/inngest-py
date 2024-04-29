from . import base, cloud_branch_env, server_kind_mismatch

_modules = (
    cloud_branch_env,
    server_kind_mismatch,
)


def create_cases(framework: str) -> list[base.Case]:
    return [module.create(framework) for module in _modules]


__all__ = ["create_cases"]
