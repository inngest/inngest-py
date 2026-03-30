# Request Lifecycle

How an execution request flows from the Inngest server through the SDK and back.

## Overview

The Inngest server (the "Executor") drives function execution by sending HTTP requests (or WebSocket messages via Connect) to the SDK. The SDK never initiates execution on its own; it only responds.

A single function _run_ typically involves **multiple requests**. Each request replays the function from the top, using memoized step results from prior requests to skip already-completed work. This replay-based model is the foundation of Inngest's durable execution.

## Entry Points

Every request enters through a **framework integration**, a thin adapter file (`flask.py`, `fast_api.py`, `django.py`, etc.) whose job is to:

1. Normalize the framework's request into a `CommRequest`
2. Pass it to `CommHandler`
3. Convert the `CommResponse` back into the framework's response format

Framework files contain no business logic.

Connect also uses `CommHandler.post()` but bypasses framework integrations. Its execution handler builds a `CommRequest` directly from the WebSocket message and calls `CommHandler` on the main thread. See [CONNECT.md](CONNECT.md).

## Signature Verification

Every `CommHandler` method is wrapped by `wrap_handler` / `wrap_handler_sync` (`_internal/comm_lib/utils.py`), which validates the inbound request signature and signs the outbound response. See [AUTH.md](AUTH.md) for details on signing keys and the fallback key rotation mechanism.

The signing key extracted during request validation is threaded into handler methods as `request_signing_key`. Some methods use it beyond auth (e.g. GET uses it to determine whether an inspection response should include sensitive details).

## CommHandler

`CommHandler` (`_internal/comm_lib/handler.py`) is the central dispatcher. It handles three HTTP methods:

| Method | Purpose                                                                                                                                           |
| ------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET`  | **Inspection.** Returns app metadata. See [INSPECTION.md](INSPECTION.md).                                                                     |
| `PUT`  | **Sync.** Registers function configurations with the Inngest server. See [SYNC.md](SYNC.md).                                                     |
| `POST` | **Execution.** Runs a function. This is the hot path described below.                                                                             |

### POST (Execution)

```
Inngest Server → POST /api/inngest?fnId=...&stepId=...
```

- **Parse query params.** Extract `fnId` (which function) and `stepId` (which step to target, if any).
- **Deserialize `ServerRequest`** from the body. Contains the triggering event, event batch, memoized step outputs, and execution context (run ID, attempt number).
- **Fetch from API if needed.** When the payload would be too large, the Executor sets `use_api=true` and the SDK fetches the event batch and step memos from the Inngest API instead.
- **Create args to pass to the function**
- **Call the function.**

### Async vs Sync

`CommHandler` supports both async and sync user functions:

- **Async functions**
- **Sync functions in an async context** Run in a thread pool to avoid blocking the event loop
- **Sync functions in a sync context** Called directly (the framework already created a thread)

## Response Format

`CommResponse.from_call_result()` converts a `CallResult` into the response the Executor expects:

| Scenario                                 | Status                                  | Body                                   |
| ---------------------------------------- | --------------------------------------- | -------------------------------------- |
| Function completed (no steps)            | 200                                     | The function's return value            |
| Step done/planned, but function not done | 206                                     | `[{ step metadata + data/error }]`     |
| Function or step error (retriable)       | 500                                     | Error object with code, message, stack |
| Non-retriable error                      | 500 + `x-inngest-no-retry: true` header | Error object                           |

Step-level results are always wrapped in a list (`multi` field on `CallResult`) and returned as 206 Partial Content. Function-level results (no steps, or function completed after all steps) are returned as 200 with the raw output value.

## Streaming

Some hosting platforms (e.g. certain serverless environments) impose idle connection timeouts. If the SDK takes too long to respond, the platform may kill the connection before the function finishes. Streaming solves this by sending keepalive bytes while the function executes, keeping the connection alive.

When enabled, the response works like this:

1. The function starts executing in an `asyncio.Task`.
2. The SDK immediately begins streaming the response (HTTP 201).
3. Every 3 seconds, a keepalive space byte is sent.
4. When execution completes, the actual result is sent as a final JSON chunk containing the body, headers, and status code that would have been the normal response.

Streaming is controlled by the `INNGEST_STREAMING` env var or the `streaming` parameter on `serve()`. It has two modes: `disable` (default) and `force`. It only applies to async functions since it relies on `asyncio.Task`. See `CommResponse.create_streaming()` in `_internal/comm_lib/models.py`.
