# Replace replay logger wrapper with a `logging.Filter`

Area: Logging
Change type: Observability

## Problem

`LoggerMiddleware` currently replaces `ctx.logger` with `FilteredLogger`, a proxy object that only intercepts a fixed list of logging methods. This means `ctx.logger` is no longer the original logger object, custom logger behavior can be missed, and the implementation currently needs a type ignore.

## Solution

Apply replay-aware filtering to the idempotent logger using a stdlib `logging.Filter` backed by the existing replay logging context variable. This keeps the user's logger object stable while suppressing records emitted during memoized-step replay.

## Related work

### Blocking

[`foundation/separate_logging.md`](./separate_logging.md) must land before or together with this spec.

The idempotent logger filter applies only to the user/function logger exposed as `ctx.logger`, which is `_loggers.user` after logging separation. SDK operational loggers under `inngest.sdk.*` must never receive this replay filter.

Before enabling the filter implementation, audit remaining `client.logger` usages and move SDK-internal diagnostics to SDK loggers. Otherwise the filter could suppress SDK operational records during memoized replay, which conflicts with this spec's scope.

Tests should prove that function logs are suppressed during memoized replay while SDK logs still emit.

### Non-blocking

[`foundation/rewrite_middleware.md`](./rewrite_middleware.md) defines the lifecycle hooks used by the implementation, including `transform_function_input`, `on_memoization_end`, and `wrap_request`.

## Out of scope

This does not replace user loggers, rewrite log records, filter SDK-internal logs, or guarantee replay filtering for loggers that do not emit through stdlib logging.

## Risks

The main risk is shared logger concurrency. A filter attached for one run must not affect another run incorrectly, and cleanup must not remove filtering still needed by another concurrent execution.

## Implementation

```python
class LoggingState(enum.Enum):
    UNMANAGED = enum.auto()
    REPLAYING = enum.auto()
    LIVE = enum.auto()


_logging_state: ContextVar[LoggingState] = ContextVar(
    "inngest_logging_state",
    default=LoggingState.UNMANAGED,
)


class StepReplayFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return _logging_state.get() is not LoggingState.REPLAYING
```

Apply the filter to `ctx.logger` for the execution scope instead of replacing `ctx.logger` with a wrapper. This keeps the logger object stable, filters stdlib logging calls uniformly, and works better with logging libraries that integrate with stdlib logging.

The logging state is internal and has three values:

- `UNMANAGED`: The current task or thread is not inside an Inngest-managed function execution scope. Records pass through.
- `REPLAYING`: The execution is replaying memoized step state before the live-code boundary. Records are suppressed.
- `LIVE`: The execution has passed the memoization boundary and is running live user code. Records pass through.

The default must be `UNMANAGED`, not replay-disabled. The filter may be attached to a shared user logger while unrelated application code is logging outside an Inngest execution scope, and those unrelated records must pass through.

The filter must preserve `LogRecord` contents exactly. User-supplied `extra` fields, `LoggerAdapter` fields, handler behavior, formatter behavior, logger levels, and methods like `exception()` must continue to behave as they would without the SDK. If `ctx.logger` is a `logging.LoggerAdapter`, attach filtering to the adapter's underlying stdlib logger while preserving the adapter object exposed to user code.

Filtering must be concurrency-safe for shared logger instances. One run must not be able to remove or disable replay filtering for another concurrent run using the same logger. The SDK must not permanently mutate user-provided loggers or handlers.

### Lifecycle

The idempotent logger lifecycle should follow the TypeScript SDK's built-in logger middleware shape while preserving Python logger identity:

- `transform_function_input` identifies the logger exposed as `ctx.logger` and installs or references the SDK-owned filter on the underlying stdlib logger.
- The request execution scope sets `_logging_state` to `REPLAYING` before user handler execution begins.
- `on_memoization_end` changes `_logging_state` to `LIVE`.
- `wrap_request` owns cleanup in a `finally` block. It must reset the `ContextVar` token and release the SDK-owned filter reference even when the request exits through success, user exceptions, internal response interrupts, middleware errors, or streaming cancellation.

Do not rely on `after_execution` or run-completion hooks for cleanup. Those hooks do not represent every request exit path, and `wrap_function_handler` may not resolve on requests where control flow is interrupted after discovering a fresh step.

The `UNMANAGED` default is only a safety fallback for shared loggers and unrelated application records. A filter that remains attached after request cleanup is still a bug because it adds overhead, can accumulate through registry mistakes, can interact badly with leaked context state, and can bleed logger state across tests or later requests.

### Context state

Replace the current `enable_logging()` and `disable_logging()` helper style. Logging state changes must use token-based `ContextVar.set()` and `ContextVar.reset()` semantics at the request scope.

```python
token = _logging_state.set(LoggingState.REPLAYING)
try:
    ...
finally:
    _logging_state.reset(token)
```

`on_memoization_end` may set the state to `LIVE` without holding its own token, because the request-scope `finally` resets the original token:

```python
_logging_state.set(LoggingState.LIVE)
```

The public helper shape should make token ownership explicit. Prefer request-scoped helpers such as `begin_logging_scope()` and `end_logging_scope(token)` plus a boundary helper such as `mark_logging_live()`. Do not keep broad `enable_logging()` and `disable_logging()` helpers that can be called without restoring the previous state.

### Shared logger registry

The SDK should install at most one SDK-owned replay filter per underlying stdlib logger.

Resolve the underlying logger as follows:

- `logging.Logger`: Use the logger itself.
- `logging.LoggerAdapter`: Use the adapter's `.logger` for filter installation, while preserving the adapter object exposed as `ctx.logger`.
- Other logger-like objects: Do not install a filter. Pass the object through unchanged.

Maintain a process-local registry keyed by the underlying logger identity. Each registry entry stores:

- The underlying `logging.Logger`.
- The single SDK-owned `StepReplayFilter` attached to that logger.
- A reference count for active Inngest request scopes using that logger.

Guard registry operations with a lock. A single global lock is sufficient because installation and removal are small critical sections.

On request start:

1. Resolve the underlying stdlib logger.
2. Acquire the registry lock.
3. If no entry exists for that logger, create one filter, attach it to the logger, and set the reference count to `1`.
4. If an entry already exists, increment its reference count.

On request cleanup:

1. Acquire the registry lock.
2. Decrement the logger entry's reference count.
3. Remove the SDK-owned filter only when the reference count reaches `0`.
4. Delete the registry entry after removing the filter.

The filter itself does not need per-run state. It reads `_logging_state`, so the same filter can safely serve concurrent executions that share one logger.

If user code or another library manually removes the SDK-owned filter from the underlying logger during an active run, that is unsupported. The SDK registry should still behave predictably:

- The registry entry remains until request cleanup decrements the reference count to `0`.
- Cleanup should attempt to remove the SDK-owned filter if it is still attached.
- Cleanup should not fail if the filter was already removed.
- A later request may reinstall the filter if no registry entry remains.

The SDK does not need to detect or repair manual filter removal during an active request. Logs emitted after manual removal may bypass replay filtering.

### Context propagation

Replay filtering relies on `ContextVar` state. That state follows normal Python context propagation rules.

Async tasks created while the request scope is active inherit the current context at task creation. If such a task logs during replay before `on_memoization_end`, its records should be suppressed. If it logs after the request scope has ended but still carries a copied replay context, that is user-created background work outside the supported request lifetime. Request cleanup must reset the parent request context, but it cannot forcibly reset context captured by detached background tasks.

Threads do not automatically inherit `ContextVar` state. Logs emitted from user-created threads during replay are not guaranteed to be suppressed unless the user explicitly propagates the context. The filter remains attached to the shared logger, but without the request `ContextVar` state the thread sees `UNMANAGED` and records pass through.

The guarantee is scoped to logs emitted on the request execution context and async tasks that participate in that context during the request lifetime.

### Logger hierarchy

The SDK installs the replay filter on the underlying stdlib logger resolved from `ctx.logger`.

This filters records handled by that exact logger. It also filters records from child loggers that propagate to the filtered logger, because stdlib propagation passes the same `LogRecord` through the filtered logger's handlers. It does not filter unrelated sibling loggers, parent loggers, or child loggers with propagation disabled unless those records pass through the filtered logger.

The SDK should not walk the logging hierarchy, attach filters to parent or child loggers, or mutate handlers to broaden filtering. Users who want replay filtering for a logger family should pass the logger that receives the propagated records as `logger=...`.

### Custom logger limitations

Replay filtering is guaranteed only for records that pass through stdlib `LogRecord` handling.

This includes normal `logging.Logger` instances and `logging.LoggerAdapter` instances, including custom subclasses that call the stdlib logging path via methods such as `super().info(...)`.

If a `logging.Logger` subclass overrides methods like `info()` and records calls without creating a `LogRecord`, the SDK-owned `logging.Filter` cannot observe or suppress those calls. The SDK should still expose that object unchanged as `ctx.logger`, but idempotent filtering is not guaranteed for those bypassed methods.

Update logger tests to capture real `LogRecord`s with a handler or to use a subclass that calls `super().info(...)`. Do not use a fake logger that records method calls without invoking stdlib logging internals to assert replay filtering.

### Tests

Add coverage for:

- Logger identity is preserved for `logging.Logger`.
- Logger identity is preserved for `logging.LoggerAdapter`.
- `LoggerAdapter` `extra` fields survive unchanged.
- Call-site `extra` fields survive unchanged.
- `logger.exception(...)` and `exc_info=True` still produce traceback records.
- Logger levels, handlers, formatters, and propagation behave as they would without the SDK filter.
- Memoized-step replay suppresses function logs.
- Memoized-step replay does not suppress SDK logs.
- Unrelated application logs using the same shared logger pass through while an Inngest run is active.
- The SDK-owned filter is removed after success.
- The SDK-owned filter is removed after user exceptions.
- The SDK-owned filter is removed after internal response interrupts.
- The SDK-owned filter is removed after middleware errors.
- The SDK-owned filter is removed after streaming cancellation.
- The `ContextVar` token is reset after every request exit path.
- Concurrent runs sharing one logger cannot remove or disable each other's filtering.
- Async tasks created during replay and awaited within the request scope inherit replay state and are filtered.
- Detached async tasks that outlive request cleanup are documented as outside the replay-filtering guarantee.
- User-created threads do not receive replay filtering unless the user explicitly propagates context.
- Manual removal of the SDK-owned filter during an active run does not crash cleanup and may allow later records to bypass filtering.
- A later request reinstalls the SDK-owned filter after an unsupported manual removal once the previous registry entry has cleaned up.
- Child loggers that propagate through the filtered logger are filtered.
- Sibling loggers, parent loggers, and child loggers with propagation disabled are not filtered unless their records pass through the filtered logger.
- Non-stdlib logger-like objects are exposed unchanged.
- Non-stdlib logger-like objects are not promised replay filtering unless they emit through stdlib `LogRecord` handling.
- `logging.Logger` subclasses that call `super()` are filtered.
- `logging.Logger` subclasses that bypass `LogRecord` handling are not used to assert replay filtering.
