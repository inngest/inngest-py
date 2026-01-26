from __future__ import annotations

import concurrent.futures
import signal
import typing

import inngest
from inngest._internal import comm_lib

from .connection import WorkerConnection, _WebSocketWorkerConnection


def connect(
    apps: list[tuple[inngest.Inngest, list[inngest.Function[typing.Any]]]],
    *,
    _experimental_thread_pool: comm_lib.ThreadPoolConfig | None = None,
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

    thread_pool = _experimental_thread_pool
    if thread_pool is None:
        # TODO: Default `enable_for_async_fns` to true in v0.6. Running async
        # functions in a thread pool should be a good default, but it's a
        # breaking change in runtime behavior.
        enable_for_async_fns = False

        # If we don't use a thread pool for sync functions then users will only
        # be able to run 1 function at a time. This is a unique requirement for
        # Connect (as opposed to Serve), since Connect doesn't have the luxury
        # of relying on HTTP frameworks (e.g. Flask) creating a thread for each
        # request.
        enabled_for_sync_fns = True

        thread_pool = comm_lib.ThreadPoolConfig(
            enable_for_async_fns=enable_for_async_fns,
            enable_for_sync_fns=enabled_for_sync_fns,
            pool=concurrent.futures.ThreadPoolExecutor(),
        )

    return _WebSocketWorkerConnection(
        apps=apps,
        instance_id=instance_id,
        rewrite_gateway_endpoint=rewrite_gateway_endpoint,
        shutdown_signals=shutdown_signals,
        max_worker_concurrency=max_worker_concurrency,
        thread_pool=thread_pool,
    )
