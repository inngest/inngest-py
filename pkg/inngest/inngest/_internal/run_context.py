from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import typing

if typing.TYPE_CHECKING:
    from inngest._internal import client_lib, execution_lib


@dataclasses.dataclass
class RunContext:
    """Execution-local state shared by client and step tools."""

    client: client_lib.Inngest
    ctx: execution_lib.Context | execution_lib.ContextSync


current_run = contextvars.ContextVar[RunContext | None](
    "inngest_run", default=None
)


@contextlib.contextmanager
def use_run(
    client: client_lib.Inngest,
    ctx: execution_lib.Context | execution_lib.ContextSync,
) -> typing.Iterator[None]:
    """Bind a run without leaking state across requests or threads."""
    token = current_run.set(RunContext(client, ctx))
    try:
        yield
    finally:
        current_run.reset(token)
