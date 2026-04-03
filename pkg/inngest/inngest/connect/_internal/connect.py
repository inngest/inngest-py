from __future__ import annotations

import contextlib
import contextvars
import dataclasses
import signal
import typing

import inngest

from .connection import WorkerConnection, WorkerConnectionImpl


def connect(
    apps: list[tuple[inngest.Inngest, list[inngest.Function[typing.Any]]]],
    *,
    instance_id: str | None = None,
    rewrite_gateway_endpoint: typing.Callable[[str], str] | None = None,
    shutdown_signals: list[signal.Signals] | None = None,
    max_worker_concurrency: int | None = None,
) -> WorkerConnection:
    """
    Create a persistent connection to an Inngest server.

    Args:
    ----
        apps: A list of tuples, where each tuple contains an Inngest client and a list of functions.
        instance_id: A stable identifier for identifying connected apps. This can be a hostname or other identifier that remains stable across restarts. It defaults to the hostname of the machine.
        rewrite_gateway_endpoint: A function that rewrites the Inngest server gateway endpoint.
        shutdown_signals: A list of graceful shutdown signals to handle. Defaults to [SIGTERM, SIGINT].
        max_worker_concurrency: The maximum number of worker concurrency to use. Defaults to None.
    """

    overrides = _get_test_overrides()

    return WorkerConnectionImpl(
        apps=apps,
        instance_id=instance_id,
        rewrite_gateway_endpoint=rewrite_gateway_endpoint,
        shutdown_signals=shutdown_signals,
        max_worker_concurrency=max_worker_concurrency,
        extend_lease_interval=overrides.extend_lease_interval,
        heartbeat_interval_sec=overrides.heartbeat_interval_sec,
    )


@dataclasses.dataclass
class _TestOverrides:
    extend_lease_interval: int | None = None
    heartbeat_interval_sec: int | None = None


_test_overides_context_var = contextvars.ContextVar[_TestOverrides](
    "test_overrides"
)


@contextlib.contextmanager
def connect_test_overrides(
    *,
    extend_lease_interval: int | None = None,
    heartbeat_interval_sec: int | None = None,
) -> typing.Generator[None, None, None]:
    """
    Set test overrides for the `connect` function.
    """

    token = _test_overides_context_var.set(
        _TestOverrides(
            extend_lease_interval=extend_lease_interval,
            heartbeat_interval_sec=heartbeat_interval_sec,
        )
    )
    try:
        yield
    finally:
        _test_overides_context_var.reset(token)


def _get_test_overrides() -> _TestOverrides:
    try:
        return _test_overides_context_var.get()
    except LookupError:
        return _TestOverrides()
