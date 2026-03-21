# Architecture

Lower-level details of the Connect implementation. For a high-level overview, see `pkg/inngest/docs/CONNECT.md`.

## Connection Lifecycle

1. **Bootstrap.** The SDK makes a REST call to `/v0/connect/start`. The server responds with a WebSocket URL, connection ID, and auth tokens.
2. **WebSocket open.** The SDK connects to the gateway URL using protobuf messages.
3. **Handshake.** The SDK receives a hello from the server, sends a `WORKER_CONNECT` message containing function configs and app metadata (same data as an HTTP sync, see `pkg/inngest/docs/SYNC.md`), and waits for a ready signal.
4. **Active.** The connection is live. The SDK receives execution requests, runs functions, and sends results.
5. **Reconnect.** On connection failure, the SDK re-runs the bootstrap and handshake. It can exclude the previous gateway to avoid reconnecting to a bad node.
6. **Shutdown.** On SIGTERM/SIGINT, the SDK sends a pause message (stop accepting new work), waits for in-flight requests to drain, and closes.

## Execution Over Connect

When the server sends an execution request over the WebSocket:

1. The SDK acknowledges receipt.
2. It builds a `CommRequest` (same as HTTP mode) and calls `CommHandler.post()`. The function runs on the main thread, not the worker thread.
3. The result is sent back as a `WORKER_REPLY` message.
4. The server acknowledges the reply.

## Lease Extensions

When the worker is processing an execution request, it periodically sends lease extension messages to the Inngest server. This is how the worker says "I'm still working on this." If lease extensions stop, the server will assume the worker has failed and may reassign the work. Lease extensions must continue for the entire duration of the execution.

## Heartbeats

The worker sends periodic heartbeat messages to the Inngest server. These must always be sent while the worker is up, including during graceful shutdown. If heartbeats stop, the server will consider the worker dead.

## Flushing

The WebSocket connection can drop at any time. If the worker has completed an execution but lost the connection before sending or receiving acknowledgment for the reply, it needs another way to deliver the result. Flushing solves this by sending unacknowledged replies via HTTP to `/v0/connect/flush`. A periodic poller checks for unacked replies and flushes them automatically.

Unacked replies are held in a buffer rather than kept in memory indefinitely, to mitigate OOM risk.

## Draining

The Inngest server may send a drain signal, telling the worker to reconnect. This can happen during server deployments or rebalancing. The worker must immediately reconnect to a new gateway, since it needs a valid WebSocket connection to continue sending heartbeats and lease extensions for in-flight work.

## Graceful Shutdown

When the worker receives a shutdown signal (SIGTERM/SIGINT):

1. Send a pause message to the Inngest server. This tells the server to stop sending new execution requests to this worker.
2. Wait for in-flight requests to finish.
3. Flush any unacknowledged replies (see Flushing above).
4. Close the WebSocket.

Heartbeats continue throughout this process.

## Threading Model

Connect internals (WebSocket connection, heartbeats, lease extensions, etc.) run in a dedicated thread. This prevents main thread blocks from interfering with Inngest server comms.

- **Main thread.** Runs user function code via `CommHandler`. Handles OS signals for graceful shutdown.
- **Worker thread.** Runs its own event loop. Manages the WebSocket, handshake, heartbeats, and message dispatch. Execution requests are forwarded to the main thread via `asyncio.run_coroutine_threadsafe()`.
