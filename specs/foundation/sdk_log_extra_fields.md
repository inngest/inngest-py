# Standardize SDK log `extra` fields

Area: Logging
Change type: Observability

## Problem

SDK operational logs need structured context for debugging and log-platform routing. Python stdlib logging supports this through `extra`, but inconsistent keys can collide with application fields, break formatters, or make dashboards and alerts harder to build.

Generic `extra` keys such as `error`, `id`, `event`, `function`, `name`, or `type` are risky because they can collide with user formatter expectations or future SDK fields. Logging raw payload data is also unsafe because event data, step output, headers, request bodies, and tokens may contain sensitive information.

## Solution

Standardize SDK-owned structured log fields. SDK operational logs may use stdlib `extra`, but SDK-provided keys must be stable, namespaced, and safe.

Use `inngest_`-prefixed keys for SDK fields:

```python
logger.warning(
    "Connect execution failed",
    extra={
        "inngest_app_id": app_id,
        "inngest_function_id": function_id,
        "inngest_run_id": run_id,
    },
)
```

Exceptions should use stdlib exception logging:

```python
try:
    ...
except Exception:
    logger.exception(
        "Failed to send Connect reply",
        extra={"inngest_run_id": run_id},
    )
```

Use `extra` for structured context, not as a substitute for tracebacks.

The SDK should maintain a documented registry of approved `inngest_*` fields. New SDK structured log fields should be added intentionally instead of relying only on a prefix convention.

## Related work

### Blocking

[`foundation/separate_logging.md`](./separate_logging.md) defines the SDK logger hierarchy. This spec applies to operational SDK logs under `inngest.sdk.*`, not user function logs emitted through `ctx.logger`.

### Non-blocking

None.

## Out of scope

This spec does not introduce a structured logging framework or require users to use JSON logging.

This spec does not constrain user logs emitted through `ctx.logger`; users own their own `extra` keys.

## Risks

Renaming `extra` keys can break downstream log searches if users already rely on current SDK fields. The current fields are not documented as stable, but release notes should still call out the change.

Overly strict field rules can slow development or hide useful diagnostics. The rules should prevent unsafe or collision-prone fields without blocking ordinary SDK debugging.

## Implementation

### Field naming

SDK `extra` keys must:

- Start with `inngest_`.
- Be stable across releases once documented.
- Use snake_case.
- Be descriptive enough to avoid generic collisions.
- Appear in the documented SDK field registry before use.

Approved fields:

- `inngest_app_id`
- `inngest_attempt`
- `inngest_env_value`
- `inngest_env_var`
- `inngest_error`
- `inngest_event_id`
- `inngest_event_name`
- `inngest_function_id`
- `inngest_function_name`
- `inngest_run_id`
- `inngest_request_id`
- `inngest_server_kind`
- `inngest_status_code`
- `inngest_step_id`
- `inngest_step_name`

Avoid unprefixed or generic keys:

- `error`
- `id`
- `event`
- `function`
- `name`
- `type`
- `run`
- `request`
- `step`

### Value safety

Values should be simple JSON-ish scalars:

- `str`
- `int`
- `float`
- `bool`
- `None`

Avoid passing arbitrary objects, models, exception objects, request objects, event objects, or payload containers in `extra`.

Do not log:

- Event payload data
- Step input or output
- Function output
- Request bodies
- Authorization headers
- Signing keys
- Tokens, secrets, or credentials
- Full HTTP headers unless each header is explicitly known to be safe

IDs such as app IDs, function IDs, run IDs, event IDs, and request IDs are acceptable when useful for debugging, even though they may be high-cardinality in some log platforms.

### Exceptions

When logging from an exception handler, prefer:

```python
logger.exception("Message", extra={...})
```

or:

```python
logger.error("Message", exc_info=True, extra={...})
```

If a searchable error string is useful, use `inngest_error` as supplemental context:

```python
logger.error(
    "Gateway send failed",
    exc_info=True,
    extra={"inngest_error": str(err)},
)
```

Do not use only `extra={"error": str(err)}` for exceptions. That loses traceback information and uses an unnamespaced key.

`inngest_error` must be conservative. It may contain short SDK-owned error codes, exception class names, or sanitized exception messages that are known not to include payloads or secrets. Do not put raw user exception messages, request URLs with credentials, headers, request bodies, event payload snippets, step output, or arbitrary `str(err)` values into `inngest_error` unless the call site has explicitly sanitized them.

When in doubt, rely on `logger.exception(...)` or `exc_info=True` for traceback capture and omit `inngest_error`.

### Migration checklist

Audit existing SDK operational logs that pass `extra={...}`:

- Replace unprefixed keys such as `error` with `inngest_error` when a supplemental string field is still useful.
- Add `exc_info=True` or use `logger.exception(...)` for exception-handler logs.
- Remove raw payloads, request bodies, headers, or arbitrary objects from `extra`.
- Add stable identifiers where useful, using namespaced keys.
- Keep user function logs untouched; this convention applies to SDK logs, not `ctx.logger` records emitted by users.

### Tests

Add a reusable test helper for SDK log records that asserts:

- Every SDK-owned `extra` key starts with `inngest_`.
- Every SDK-owned `extra` key appears in the approved field registry.
- SDK `extra` values are simple scalars: `str`, `int`, `float`, `bool`, or `None`.
- SDK log records do not include known unsafe generic keys such as `error`, `id`, `event`, `function`, `name`, `type`, `run`, `request`, or `step`.

Use this helper in tests that exercise SDK operational logs. The helper should inspect emitted `LogRecord` objects instead of trying to statically parse every logging call.

Add focused tests for:

- Exception-handler logs use `logger.exception(...)` or `exc_info=True`.
- `inngest_error` is omitted for raw user or payload-derived exceptions unless the value is explicitly sanitized.
- User function logs emitted through `ctx.logger` are not constrained by this SDK `extra` convention.
