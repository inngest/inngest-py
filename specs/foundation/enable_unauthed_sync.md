# Default unauthenticated sync to disabled

Area: Config
Change type: Security

## Problem

Unauthenticated cloud sync is currently opt-out. In cloud mode, `serve(enable_unauthed_sync=None)` allows unsigned out-of-band sync PUT requests unless `INNGEST_ENABLE_UNAUTHED_SYNC=false` is set.

That means a cloud-mode app can accept unsigned sync PUT requests by default, even though signed sync is available and should be the normal production behavior.

## Solution

Keep the public `enable_unauthed_sync: bool | None = None` parameter, but change the cloud-mode effective default to `False`.

Unsigned out-of-band sync remains available as an explicit compatibility escape hatch. Dev mode continues to allow unsigned sync because the Dev Server does not sign sync requests.

## Out of scope

This does not change Dev Server sync behavior, in-band sync signing requirements, or SDK-to-Inngest API authentication for out-of-band registration.

This does not add authenticated sync support for self-hosted deployments.

## Risks

Some existing cloud-mode deployments may rely on unsigned out-of-band sync. Those users must explicitly opt in with `serve(enable_unauthed_sync=True)` or `INNGEST_ENABLE_UNAUTHED_SYNC=true`.

The main affected groups are:

- Self-hosted users, because authenticated sync support for self-hosted deployments does not exist yet.
- Programmatic sync users, who can migrate to authenticated Inngest REST API requests instead of sending unsigned sync PUTs.

## Implementation

### Documentation

User-facing documentation for this change must tell users who currently rely on unsigned out-of-band sync to opt in explicitly. The two common cases are self-hosted deployments and programmatic sync callers.

Self-hosted deployments do not yet have authenticated sync support, so those users must continue enabling unauthenticated sync until authenticated self-hosted sync exists.

Programmatic sync callers can either opt in explicitly or replace unsigned sync PUTs with authenticated requests to the Inngest REST API.

### Behavior

Cloud-mode behavior:

- `serve(enable_unauthed_sync=True)` explicitly allows unsigned out-of-band sync PUT requests.
- `serve(enable_unauthed_sync=False)` rejects unsigned or invalidly signed out-of-band sync PUT requests.
- `serve(enable_unauthed_sync=None)` reads `INNGEST_ENABLE_UNAUTHED_SYNC`.
- `INNGEST_ENABLE_UNAUTHED_SYNC=true` or `INNGEST_ENABLE_UNAUTHED_SYNC=1` explicitly allows unsigned out-of-band sync PUT requests.
- `INNGEST_ENABLE_UNAUTHED_SYNC=false`, `INNGEST_ENABLE_UNAUTHED_SYNC=0`, an empty value, or an unset value rejects unsigned or invalidly signed out-of-band sync PUT requests.
- Unrecognized `INNGEST_ENABLE_UNAUTHED_SYNC` values, such as `yes`, `on`, or `garbage`, also reject unsigned or invalidly signed out-of-band sync PUT requests.

Environment variable parsing must fail closed. After trimming whitespace and lowercasing, only `true` and `1` enable unauthenticated sync. Every other value disables unauthenticated sync.

For non-empty unrecognized values, the SDK should log a warning through the SDK sync logger. The warning should name `INNGEST_ENABLE_UNAUTHED_SYNC`, explain that unauthenticated sync remains disabled, and follow the SDK namespaced `extra` convention.

The `enable_unauthed_sync` argument takes precedence over `INNGEST_ENABLE_UNAUTHED_SYNC`. Cloud in-band sync must still require a valid signed request regardless of this setting.

Cloud-mode out-of-band sync should fail closed with minimal information when unauthenticated sync is disabled. Missing, malformed, or invalid request signatures must return the normal unauthorized response before any detailed server-kind mismatch response, including when the request claims `x-inngest-server-kind: dev`. If the request has a valid signature, or unauthenticated sync is explicitly enabled, the handler may continue to normal sync validation and return server-kind mismatch errors.

Dev mode ignores this opt-out and continues to allow sync because the Dev Server does not sign sync requests. Dev mode may bypass sync signature validation only for requests accepted as Dev Server traffic. Requests classified as Cloud traffic in Dev mode must be rejected as server-kind mismatches, not accepted through the Dev Server unsigned-sync path. For accepted Dev Server sync requests, the SDK must not require or validate sync signatures; unsigned requests and requests with present but malformed or invalid signature headers are accepted.

This setting only controls whether the incoming sync PUT may be unsigned. Out-of-band sync still sends an authenticated SDK-to-Inngest API registration request.

## Testing

Add explicit coverage for:

- Cloud mode defaults to rejecting unsigned out-of-band sync PUT requests.
- Explicit `enable_unauthed_sync` arguments take precedence over `INNGEST_ENABLE_UNAUTHED_SYNC`.
- Environment parsing enables unauthenticated sync only for recognized true values; false, empty, unset, and unrecognized values disable it.
- Invalid environment values fail closed and emit an SDK warning that follows the namespaced `extra` convention.
- Cloud in-band sync still requires a valid signed request regardless of this setting.
- Cloud mode with unauthenticated sync disabled returns unauthorized before detailed server-kind mismatch for unsigned or invalidly signed out-of-band sync PUTs.
- Dev mode accepts Dev Server unsigned sync, including malformed or invalid signature headers, but rejects requests classified as Cloud traffic.

## References

- [`foundation/separate_logging.md`](./separate_logging.md) defines the SDK logger hierarchy used for invalid environment variable warnings.
- [`foundation/sdk_log_extra_fields.md`](./sdk_log_extra_fields.md) defines the namespaced `extra` field convention used by those warnings.
- [Programmatic app sync with the Inngest REST API](https://www.inngest.com/docs/apps/cloud#programmatically)
