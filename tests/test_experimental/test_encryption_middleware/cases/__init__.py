import inngest
from inngest._internal import server_lib

from . import (
    base,
    decrypt_event,
    decrypt_only,
    decrypt_unexpected_encryption_field,
    encrypt_overridden_encryption_field,
    fallback_decryption_key,
    step_and_fn_output,
)

_modules = (
    decrypt_event,
    decrypt_only,
    decrypt_unexpected_encryption_field,
    encrypt_overridden_encryption_field,
    fallback_decryption_key,
    step_and_fn_output,
)


def create_async_cases(
    client: inngest.Inngest,
    framework: server_lib.Framework,
) -> list[base.Case]:
    return [
        module.create(client, framework, is_sync=False) for module in _modules
    ]


def create_sync_cases(
    client: inngest.Inngest,
    framework: server_lib.Framework,
) -> list[base.Case]:
    cases = []
    for module in _modules:
        case = module.create(client, framework, is_sync=True)
        if isinstance(case.fn, list) and len(case.fn) == 0:
            continue
        cases.append(case)

    return cases


__all__ = ["create_async_cases", "create_sync_cases"]
