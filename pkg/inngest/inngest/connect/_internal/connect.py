from __future__ import annotations

import signal
import typing

import inngest

from .connection import WorkerConnection, _WebSocketWorkerConnection


def connect(
    apps: list[tuple[inngest.Inngest, list[inngest.Function[typing.Any]]]],
    *,
    instance_id: str | None = None,
    rewrite_gateway_endpoint: typing.Callable[[str], str] | None = None,
    shutdown_signals: list[signal.Signals] | None = None,
) -> WorkerConnection:
    """
    Create a persistent connection to an Inngest server.

    Args:
    ----
        apps: A list of tuples, where each tuple contains an Inngest client and a list of functions.
        instance_id: A stable identifier for identifying connected apps. This can be a hostname or other identifier that remains stable across restarts. It defaults to the hostname of the machine.
        rewrite_gateway_endpoint: A function that rewrites the Inngest server gateway endpoint.
        shutdown_signals: A list of graceful shutdown signals to handle. Defaults to [SIGTERM, SIGINT].
    """
    return _WebSocketWorkerConnection(
        apps=apps,
        instance_id=instance_id,
        rewrite_gateway_endpoint=rewrite_gateway_endpoint,
        shutdown_signals=shutdown_signals,
    )
