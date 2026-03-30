# Authentication and Signing

How the SDK authenticates requests from the Inngest server and authenticates its own outbound requests.

All auth logic lives in `_internal/net.py`.

## Signing Keys

The SDK supports two signing keys:

- **Primary signing key.** The main key used for signing and verification.
- **Fallback signing key.** An optional second key that enables zero-downtime signing key rotation. When rotating keys, set the new key as primary and the old key as fallback. Both will be accepted until the fallback is removed.

In production, a signing key is required. In dev mode, signature verification is skipped.

## Inbound Requests (Executor to SDK)

When the Inngest server sends an execution request, the SDK validates the request signature:

1. Validate the signature header against the request body using the primary signing key.
2. If that fails and a fallback key exists, retry validation with the fallback key.
3. If both fail and the handler requires a signature, return 401 immediately.

Only POST requires a valid signature at the `wrap_handler` level (`require_signature=True`). GET and PUT use `require_signature=False`, meaning `wrap_handler` won't reject unsigned requests. However, PUT enforces signing itself for in-band sync (returns 401 if the request isn't signed). Out-of-band sync and GET work without a signature, though GET returns a limited response when unsigned (see [INSPECTION.md](INSPECTION.md)).

Connect requests skip signature verification entirely because they use WebSocket-level auth rather than per-request signatures.

After execution, if the inbound request was signed, the SDK signs its response body with the same key so the Executor can verify it.

This is implemented by `validate_request_sig()` in `_internal/net.py`, called from the `wrap_handler`/`wrap_handler_sync` decorators in `_internal/comm_lib/utils.py`.

## Outbound Requests (SDK to Inngest API)

The SDK makes outbound requests to the Inngest API in two cases:

- **Sync (registration).** PUT handler sends function configs to the API.
- **Fetching memos/batches.** When the Executor sets `use_api=true`, the SDK fetches step memos and event batches from the API.

For these requests, the signing key hash is sent as a Bearer token in the Authorization header. The fallback key works the same way: if the API responds with 401 or 403, the SDK retries the request with the fallback key.

This is implemented by `fetch_with_auth_fallback()` and `fetch_with_auth_fallback_sync()`.
