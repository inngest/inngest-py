# Separate SDK-internal logging from function logging

Area: Logging
Change type: Observability

## Problem

The client logger is used for both SDK internals and `ctx.logger`. A single logger controls operational SDK diagnostics and user function logs, which makes production logging noisy and difficult to configure. It also means `set_logger()` can mutate logger behavior after client construction.

Users need `ctx.logger` to behave like their normal application logger, while SDK internals need their own operational logging hierarchy.

## Solution

Separate SDK-internal logging from function logging. SDK internals use an `inngest.sdk.*` logger hierarchy. User function code uses the idempotent logger exposed as `ctx.logger`.

If a user passes `logger=...` to `Inngest(...)`, that same object is exposed as `ctx.logger` during function execution. If no logger is passed, `ctx.logger` defaults to `logging.getLogger("inngest.functions")`.

## Related work

### Blocking

None.

### Non-blocking

[`foundation/use_logging_filter.md`](./use_logging_filter.md) defines the idempotent logger implementation that should be layered onto `_loggers.user` after logging roles are separated. This spec establishes the logger ownership model that the filter depends on: SDK operational loggers under `inngest.sdk.*` must not be replay-filtered, and `ctx.logger` must remain the user/function logger.

The SDK must not implement idempotent logging by replacing `ctx.logger` with a wrapper. Before v0.6 release, logging separation and the filter-based idempotent logger behavior must both land so the user-visible `ctx.logger` identity guarantee is preserved.

[`foundation/rewrite_middleware.md`](./rewrite_middleware.md) defines the `on_memoization_end` lifecycle hook that marks the transition from memoized replay to live user code. The logging filter should use that boundary to enable user function logs and should use wrapper/finally-style cleanup to reset logging state after success, user errors, internal response interrupts, middleware failures, and cancellation.

[`foundation/sdk_log_extra_fields.md`](./sdk_log_extra_fields.md) defines stable, namespaced `extra` fields for SDK operational logs emitted under the `inngest.sdk.*` hierarchy.

## Out of scope

This does not introduce a new logging framework, structured logging API, or non-stdlib logger adapter. Non-stdlib integrations are supported only when they emit through stdlib logging.

## Risks

Logger configuration is often application-specific. The main risk is surprising users by changing where SDK messages appear or by accidentally altering their logger object. The implementation must preserve user logger identity and avoid permanent mutations to user-provided loggers or handlers.

## Implementation

Add a public logger protocol for user-facing logger values:

```python
class LoggerLike(typing.Protocol):
    def debug(self, msg: object, *args: typing.Any, **kwargs: typing.Any) -> typing.Any: ...
    def info(self, msg: object, *args: typing.Any, **kwargs: typing.Any) -> typing.Any: ...
    def warning(self, msg: object, *args: typing.Any, **kwargs: typing.Any) -> typing.Any: ...
    def error(self, msg: object, *args: typing.Any, **kwargs: typing.Any) -> typing.Any: ...
    def exception(self, msg: object, *args: typing.Any, **kwargs: typing.Any) -> typing.Any: ...
    def critical(self, msg: object, *args: typing.Any, **kwargs: typing.Any) -> typing.Any: ...
    def log(self, level: int, msg: object, *args: typing.Any, **kwargs: typing.Any) -> typing.Any: ...
```

Export this protocol as `inngest.LoggerLike`. It intentionally models the common logging method surface with permissive `*args` and `**kwargs`, so `logging.Logger`, `logging.LoggerAdapter`, and many stdlib-compatible third-party loggers type-check without forcing one concrete logger class.

The constructor should be typed as `logger: LoggerLike | None = None`. Runtime should remain permissive and pass through any object supplied with `logger=...` unchanged; the type annotation only describes the supported static contract.

`ctx.logger` should be statically typed as `LoggerLike`. The runtime object is still the exact object passed to `Inngest(logger=...)`, but static typing exposes only the portable logger protocol. Users who need custom logger-specific methods or attributes can narrow or cast `ctx.logger` to their concrete logger type in their own code.

Replace the current overloaded `Inngest.logger` attribute with explicit client logger roles:

```python
@dataclasses.dataclass(frozen=True)
class ClientLoggers:
    user: LoggerLike
    sdk: logging.Logger
```

`Inngest` should store these as a private container:

```python
self._loggers = ClientLoggers(
    user=logger or logging.getLogger("inngest.functions"),
    sdk=logging.getLogger("inngest.sdk.client"),
)
```

`_loggers.user` is the user-provided logger. It is exposed as `ctx.logger` during function execution and used only where the SDK is intentionally acting on behalf of user function code.

`_loggers.sdk` is the SDK operational logger for client-owned diagnostics, such as mode detection, branch-environment warnings, and event sending. Other SDK modules should use their own `inngest.sdk.*` module-level loggers instead of reaching for the user logger.

Remove the public `client.logger` attribute in v0.6. Internal code must choose either `_loggers.user` for context construction or an SDK logger for operational diagnostics.

Suggested SDK logger hierarchy:

- `inngest.sdk.connect` for Connect lifecycle, heartbeats, handshakes, leases, and WebSocket errors
- `inngest.sdk.comm` for HTTP handler, sync, request parsing, and signature verification
- `inngest.sdk.client` for event sending, mode detection, and client-side API calls
- `inngest.sdk.framework` or adapter-specific names such as `inngest.sdk.flask`, `inngest.sdk.fast_api`, `inngest.sdk.django`, `inngest.sdk.tornado`, and `inngest.sdk.digital_ocean` for framework adapter diagnostics
- `inngest.functions` as the default `ctx.logger` when users do not pass a logger

Users can then configure SDK verbosity independently from function logs:

```python
logging.getLogger("inngest.sdk.connect").setLevel(logging.WARNING)
logging.getLogger("inngest.sdk").setLevel(logging.WARNING)
```

### Default logging behavior

The SDK should behave like a normal Python library. It may obtain named loggers and emit records, but it must not configure application logging by default.

The SDK must not:

- Attach handlers to SDK loggers or user/default function loggers.
- Set logger levels on SDK loggers or user/default function loggers.
- Change propagation on SDK loggers or user/default function loggers.
- Install a `NullHandler` unless a later explicit decision documents why it is needed.
- Mutate handlers, formatters, filters, or levels provided by the application, except for the scoped idempotent logging filter described in [`foundation/use_logging_filter.md`](./use_logging_filter.md).

Users route SDK logs to their logging platform through normal stdlib logging configuration:

```python
handler = MyPlatformHandler()
sdk_logger = logging.getLogger("inngest.sdk")
sdk_logger.setLevel(logging.INFO)
sdk_logger.addHandler(handler)
```

Helper APIs that only log SDK diagnostics must not accept or use the user logger. Prefer module-level SDK loggers in the module that owns the diagnostic:

```python
logger = logging.getLogger("inngest.sdk.comm")
```

For current helper call sites:

- `CommResponse.from_error(...)` and `CommResponse.unauthorized(...)` should stop receiving `client.logger`. They should use an `inngest.sdk.comm` logger internally or accept an explicitly named `sdk_logger` parameter only when dependency injection is needed for tests.
- `Syncer` should use `logging.getLogger("inngest.sdk.comm.sync")` or receive an explicitly named SDK logger.
- `wrap_handler` and comm handler helpers should use `inngest.sdk.comm` loggers for request parsing, sync, signature verification, and response construction diagnostics.
- Framework adapters and `_to_response` helpers should use adapter SDK loggers, not the user logger.
- Client-owned diagnostics such as mode detection, branch-environment warnings, and event sending may use `client._loggers.sdk`.

Connect needs special care because a single worker connection can serve multiple clients. Connection lifecycle logs must never inherit one client's user logger. `WorkerConnectionImpl` and connection-wide handlers should use SDK Connect loggers:

- `inngest.sdk.connect` for connection lifecycle
- `inngest.sdk.connect.heartbeat` for heartbeat send/receive paths
- `inngest.sdk.connect.handshake` for gateway handshake and sync startup
- `inngest.sdk.connect.execution` for executor request dispatch and reply handling
- `inngest.sdk.connect.drain` for drain handling

When a Connect execution request is dispatched to a specific client/function, context construction should use that selected client's `_loggers.user` for `ctx.logger`. Operational Connect diagnostics should still use SDK Connect loggers. If a Connect diagnostic needs app, function, run, or request identifiers, include them with `extra` instead of changing logger identity.

### Migration checklist

Audit every current `client.logger` use and move it to the correct role:

- Client-owned diagnostics in `client_lib/client.py`, including `_get_mode`, constructor mode decisions, branch-environment warnings, and event sending, should use `client._loggers.sdk`.
- Context construction in execution models should use `client._loggers.user` for `ctx.logger`.
- Mocked trigger utilities that construct contexts should use `client._loggers.user` when they are simulating user function execution.
- `comm_lib.models`, `comm_lib.utils`, `comm_lib.handler`, `CommResponse.from_error(...)`, `CommResponse.unauthorized(...)`, and `Syncer` should use `inngest.sdk.comm` or `inngest.sdk.comm.sync` loggers.
- Framework adapters for Flask, FastAPI, Django, Tornado, and DigitalOcean should use adapter SDK loggers for SDK diagnostics and should not pass user loggers into response helpers.
- Connect connection and handler code under `connect/_internal` should use `inngest.sdk.connect.*` loggers for operational diagnostics.
- Connect execution context construction should use the selected client's `_loggers.user` for `ctx.logger`.
- `LoggerMiddleware` should stop replacing `ctx.logger` and should rely on the filter behavior from [`foundation/use_logging_filter.md`](./use_logging_filter.md).
- `experimental/sentry_middleware.py` should not use the user logger for SDK or middleware initialization diagnostics; use a package or SDK logger.
- `pkg/inngest_encryption` should not depend on `client.logger` in its v0.6-compatible serializer implementation. Operational encryption diagnostics should use a package logger.
- Tests and examples should pass `logger=` to `Inngest(...)` instead of mutating `client.logger` or calling `set_logger()`.

After migration, `client.logger` should have no internal call sites.

`ctx.logger` is the idempotent logger for user function code. It should feel like the user's normal stdlib logger or logger adapter, except that records emitted while replaying memoized steps are suppressed so function logs are idempotent across re-execution.

The idempotent logger must preserve normal stdlib logging behavior, including custom `extra` fields, `LoggerAdapter`-provided fields, handlers, formatters, levels, and methods like `exception()`. A replay filter should only decide whether a `LogRecord` is emitted; it must not rewrite or remove record attributes.

If `ctx.logger` is a `logging.LoggerAdapter`, replay filtering should apply to the adapter's underlying stdlib logger while keeping the adapter object visible to user code. Non-stdlib logger objects are supported only to the extent that they emit through stdlib logging; otherwise the SDK cannot guarantee replay-aware filtering without replacing the logger.

### Non-stdlib loggers

The SDK should not reject non-stdlib logger objects passed with `logger=...`. If a user passes a structlog, loguru, or other logger-like object, the SDK should expose that same object unchanged as `ctx.logger`.

The guarantee boundary is narrower for these objects:

- Full identity-preserving idempotent logging guarantees apply to `logging.Logger` and `logging.LoggerAdapter`.
- Non-stdlib logger objects are passed through unchanged.
- Static typing for non-stdlib loggers is limited to the `LoggerLike` protocol unless users cast to their concrete logger type.
- Replay-aware filtering is guaranteed only when the logger emits through stdlib `LogRecord` handling.
- The SDK must not wrap or adapt non-stdlib loggers to simulate filtering, because doing so would reintroduce an incomplete proxy object.

Users who want replay-aware filtering with structlog should configure structlog's stdlib integration and pass a stdlib-compatible logger or adapter. Examples and docs should not imply that plain `structlog.get_logger()` receives SDK replay filtering unless it is configured to emit through stdlib logging.

SDK internals must never log through `ctx.logger`. Operational SDK logs must use module-level loggers under `inngest.sdk.*`.

SDK-internal error logs should include tracebacks when logging from an exception handler, using `logger.exception(...)` or `logger.error(..., exc_info=True)`.

### Public API changes

- Remove `Inngest.set_logger()`. Logger configuration becomes constructor-only.
- Keep the constructor `logger` argument for `ctx.logger`; it configures the user-facing idempotent logger only.
- Do not use the user-facing function logger for SDK-internal logs.

Logger selection is frozen at `Inngest(...)` construction. Users who want a custom `ctx.logger` must pass it with `logger=` when constructing the client:

```python
logger = logging.getLogger("my-app.functions")
client = inngest.Inngest(app_id="my-app", logger=logger)
```

Function registration must not create an independent logger snapshot. Context construction should use `client._loggers.user`, which is stable because `set_logger()` no longer exists.

`Inngest.set_logger()` should be removed outright in v0.6 rather than kept as a deprecated shim. Tests and examples that currently mutate the logger after client construction should construct the client with `logger=...` instead.

Tests and examples that currently assert against `client.logger` should be migrated to constructor injection plus captured `ctx.logger` behavior. Public tests should verify that a logger passed with `logger=` is exposed unchanged inside the function context. Internal tests may inspect `client._loggers.user` only when they are specifically testing client internals.

### Tests

Add constructor and public API tests:

- `logger=` is exposed unchanged as `ctx.logger`.
- The default `ctx.logger` is `logging.getLogger("inngest.functions")`.
- `Inngest.set_logger()` is not present.
- `client.logger` is not present.
- `ctx.logger` is typed as `LoggerLike`.
- `logging.Logger`, `logging.LoggerAdapter`, and a custom protocol-compatible logger satisfy the public `logger=` type.
- Function registration does not snapshot a separate logger.
- Existing tests that asserted against `client.logger` are migrated to constructor injection and captured `ctx.logger` assertions.

Add logger separation tests:

- SDK operational logs are emitted under `inngest.sdk.*`.
- SDK operational logs do not reach a user-provided `ctx.logger`.
- User function logs emitted through `ctx.logger` do not use SDK loggers.
- Client-owned diagnostics use `client._loggers.sdk`.

Add idempotent logger compatibility tests:

- `logging.Logger` identity is preserved.
- `logging.LoggerAdapter` identity is preserved.
- `LoggerAdapter` `extra` fields are preserved.
- Call-site `extra` fields are preserved.
- Handlers, levels, formatters, and propagation behave as they would without the SDK.
- `logger.exception(...)` and `logger.error(..., exc_info=True)` preserve traceback behavior.
- Replay filtering suppresses memoized-step replay logs without suppressing unrelated application logs using the same shared logger.
- Concurrent runs sharing one logger cannot remove or disable each other's replay filtering.

Add operational path tests:

- Connect connection lifecycle logs use `inngest.sdk.connect` or child loggers.
- Connect execution context construction still uses the selected client's `_loggers.user` for `ctx.logger`.
- HTTP comm errors use `inngest.sdk.comm`.
- Syncer logs use `inngest.sdk.comm.sync`.
- Framework adapter error paths use adapter SDK loggers.

Add non-stdlib logger tests:

- A non-stdlib logger-like object passed with `logger=` is exposed unchanged as `ctx.logger`.
- The SDK does not wrap or adapt the non-stdlib logger.
- Replay filtering is not asserted for non-stdlib loggers unless the test logger emits through stdlib `LogRecord` handling.
