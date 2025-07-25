import inngest
from inngest._internal import server_lib

from . import (
    base,
    decrypt_event,
    decrypt_only,
    decrypt_unexpected_encryption_field,
    encrypt_overridden_encryption_field,
    fallback_decryption_key,
    invoke,
    invoke_custom_encryption_field,
    send_event,
    send_event_custom_encryption_field,
    step_and_fn_output,
)

_modules = (
    decrypt_event,
    decrypt_only,
    decrypt_unexpected_encryption_field,
    encrypt_overridden_encryption_field,
    fallback_decryption_key,
    invoke,
    invoke_custom_encryption_field,
    send_event,
    send_event_custom_encryption_field,
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
    cases: list[base.Case] = []
    for module in _modules:
        case = module.create(client, framework, is_sync=True)
        if not isinstance(case.fn, inngest.Function) and len(case.fn) == 0:
            continue

        cases.append(case)

    return cases
