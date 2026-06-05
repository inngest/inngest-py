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

GET and POST require a valid signature at the `wrap_handler` level (`require_signature=True`) in cloud mode, returning 401 for unsigned or invalid requests. In dev mode, signature validation is skipped for every HTTP method.

PUT app sync requests also use `require_signature=False` by default. This preserves compatibility with unauthenticated out-of-band sync requests. Users can opt out by setting `INNGEST_ENABLE_UNAUTHED_SYNC=false` or passing `enable_unauthed_sync=False` to `serve()`, which makes cloud-mode PUT sync reject unsigned or invalidly signed requests with 401. Dev mode ignores this opt-out because the Dev Server does not send signed requests.

Cloud in-band sync still requires a signed PUT, since the response carries a signed body that the server validates. Dev mode falls back to out-of-band sync because the Dev Server does not sign requests.

All auth failures intentionally return the same minimal 401 response body: `{"message":"Unauthorized"}`. The response does not include SDK version, framework, environment, expected server kind, error code, or validation details.

Connect requests skip signature verification entirely because they use WebSocket-level auth rather than per-request signatures.

After execution, if the inbound request was signed, the SDK signs its response body with the same key so the Executor can verify it.

This is implemented by `validate_request_sig()` in `_internal/net.py`, called from the `wrap_handler`/`wrap_handler_sync` decorators in `_internal/comm_lib/utils.py`.

## Outbound Requests (SDK to Inngest API)

The SDK makes outbound requests to the Inngest API in two cases:

- **Sync (registration).** PUT handler sends function configs to the API.
- **Fetching memos/batches.** When the Executor sets `use_api=true`, the SDK fetches step memos and event batches from the API.

For these requests, the signing key hash is sent as a Bearer token in the Authorization header. The fallback key works the same way: if the API responds with 401 or 403, the SDK retries the request with the fallback key.

This is implemented by `fetch_with_auth_fallback()` and `fetch_with_auth_fallback_sync()`.
