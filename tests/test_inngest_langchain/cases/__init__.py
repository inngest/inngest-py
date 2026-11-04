import inngest
from inngest._internal import server_lib

from . import base, parallel_tool_calls, single_tool_call

_modules = (parallel_tool_calls, single_tool_call)


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
    return [
        module.create(client, framework, is_sync=True) for module in _modules
    ]
