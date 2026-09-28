"""
Execution-local context bound by Function.call and call_sync.

The binding covers execution, including transform_input, before_execution,
after_execution, and send hooks invoked there. It is reset before
transform_output and before_response, even on failure. Concurrent executions
have separate bindings.  Sync handlers bind inside call_sync in whichever thread
executes the call, including the worker thread used by HTTP/Connect's async
dispatch path.
"""

from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import typing

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, execution_lib


@dataclasses.dataclass
class RunContext:
    """
    Execution-local state shared by client and step tools.
    """

    ctx: execution_lib.Context | execution_lib.ContextSync
    client: client_lib.Inngest


current_run = contextvars.ContextVar[RunContext | None](
    "inngest_run", default=None
)


@contextlib.contextmanager
def use_run(
    ctx: execution_lib.Context | execution_lib.ContextSync,
    client: client_lib.Inngest,
) -> typing.Iterator[None]:
    """
    Bind a run without leaking state across requests or threads.
    """

    token = current_run.set(RunContext(ctx, client))
    try:
        yield
    finally:
        current_run.reset(token)


def get_sessions(
    *, client: client_lib.Inngest | None = None
) -> dict[str, str] | None:
    """
    Read the active context's mutable sessions at call time, if bound.

    Client sends pass their client to restrict inheritance to the run's owner.
    Step tools already belong to the run and do not need this check.
    """

    run = current_run.get()
    if run is None or (client is not None and run.client is not client):
        return None
    return run.ctx.sessions
