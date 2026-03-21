# Sync

How the SDK registers its app with the Inngest server.

## Overview

Before the Inngest server can execute functions, it needs to know they exist. Syncing is the process of sending function configurations (triggers, concurrency limits, retry policies, etc.) to the server. The SDK supports two sync mechanisms: **in-band** and **out-of-band**.

Syncing is triggered by the Inngest server sending a PUT request to the SDK's serve endpoint. The `x-inngest-sync-kind` header determines which mechanism is used.

## In-Band Sync

The SDK responds directly to the PUT request with all function configs and app metadata. This is the preferred mechanism.

**Request flow:**

1. Inngest server sends PUT with `x-inngest-sync-kind: in_band` header.
2. SDK verifies the request signature (required for in-band sync).
3. SDK responds with an `InBandSynchronizeResponse`.

In-band sync is enabled by default. It can be disabled via `INNGEST_ALLOW_IN_BAND_SYNC=false`, which forces out-of-band sync.

## Out-of-Band Sync

The SDK makes a separate HTTP POST to the Inngest API's `/fn/register` endpoint. Used as a fallback when in-band sync is disabled.

**Request flow:**

1. Inngest server sends PUT (without in-band header, or in-band is disabled).
2. SDK builds a `SynchronizeRequest` with app metadata and function configs.
3. SDK POSTs this to `{api_origin}/fn/register`, authenticated with the signing key hash as a Bearer token (see [AUTH.md](AUTH.md)).
4. SDK forwards the API's response back to the original PUT caller.

## Function Configs

Both sync mechanisms send the same function configuration data, built by `Function.get_config()` in `_internal/function.py`.

On-failure handlers are registered as separate functions. Their ID is `{parent_id}-failure` and they trigger on the `inngest/function.failed` internal event, filtered by the parent function's ID.

## Connect

Connect uses a WebSocket-based handshake instead of HTTP PUT. During the handshake, the SDK sends a `WORKER_CONNECT` protobuf message that includes the same function configs (JSON-encoded). The runtime URLs use `wss://connect` instead of HTTP URLs, and the runtime type is `ws` instead of `http`. See `connect/_internal/init_handshake_handler.py`.

## Server Kind Validation

Both sync mechanisms validate that the server kind (dev vs cloud) matches the SDK's mode. A Dev Server sync request to a production SDK (or vice versa) is rejected with `SERVER_KIND_MISMATCH`.
