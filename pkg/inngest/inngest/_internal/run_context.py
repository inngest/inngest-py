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
    from inngest._internal import client_lib, execution_lib, step_lib


@dataclasses.dataclass
class RunContext:
    """
    Execution-local state shared by client and step tools.
    """

    ctx: execution_lib.Context | execution_lib.ContextSync
    client: client_lib.Inngest


@dataclasses.dataclass
class ExperimentContext:
    """Attribution for steps discovered in a variant callback."""

    opts: dict[str, object]
    found_step: bool = False


current_run = contextvars.ContextVar[RunContext | None](
    "inngest_run", default=None
)
# ReportedStep binds this for nesting checks and metadata attribution.
current_step: contextvars.ContextVar[step_lib.StepInfo | None] = (
    contextvars.ContextVar("inngest_step", default=None)
)
current_experiment = contextvars.ContextVar[ExperimentContext | None](
    "inngest_experiment", default=None
)


@dataclasses.dataclass(frozen=True)
class Span:
    """
    A trace group that steps discovered inside it belong to.

    origin is the library that created the span for the user, like
    "inngest-py@1.0.0". Steps inherit the innermost span's origin.
    """

    id: str
    name: str
    kind: str | None = None
    origin: str | None = None

    def to_dict(self) -> dict[str, str]:
        d = {"id": self.id, "name": self.name}
        if self.kind is not None:
            d["kind"] = self.kind
        if self.origin is not None:
            d["origin"] = self.origin
        return d


current_span = contextvars.ContextVar[tuple[Span, ...]](
    "inngest_span", default=()
)


@contextlib.contextmanager
def use_span(span: Span) -> typing.Iterator[None]:
    """
    Group steps discovered inside the block under span, nested in any
    enclosing span.
    """

    path = current_span.get()
    if span.origin is None and len(path) > 0:
        span = dataclasses.replace(span, origin=path[-1].origin)
    token = current_span.set((*path, span))
    try:
        yield
    finally:
        current_span.reset(token)


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


def prepare_step(step: step_lib.StepInfo) -> None:
    """
    Attach experiment attribution and trace spans during discovery, including
    replay.
    """
    experiment = current_experiment.get()
    if experiment is not None:
        experiment.found_step = True
        step.opts = {**(step.opts or {}), **experiment.opts}

    path = current_span.get()
    if len(path) > 0:
        opts = {**(step.opts or {}), "span": [s.to_dict() for s in path]}
        # The step's own origin wins, then the innermost span's.
        if "origin" not in opts and path[-1].origin is not None:
            opts["origin"] = path[-1].origin
        step.opts = opts
