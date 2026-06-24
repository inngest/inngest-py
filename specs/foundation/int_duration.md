# Require `datetime.timedelta` for duration parameters

Area: Config
Change type: Quality of life

## Problem

Public duration and timeout parameters currently accept `int | datetime.timedelta`, where `int` means milliseconds. Python's numeric timeout convention is seconds, not milliseconds. For example, `time.sleep(5)`, `asyncio.wait_for(..., timeout=5)`, and `httpx.Timeout(5)` all use seconds.

The current SDK convention makes `ctx.step.sleep("id", 5)` mean 5ms, which is surprising and easy to misuse.

## Solution

Public duration and timeout parameters should only accept `datetime.timedelta`. This makes call sites explicit and removes the SDK-specific milliseconds convention from the public API.

## Related work

### Blocking

None.

### Non-blocking

None.

## Out of scope

This does not change wire duration units, internal timestamp representation, or APIs that already require absolute `datetime.datetime` values.

## Risks

This is a breaking change for users passing integers today. The migration is straightforward, but the SDK should produce clear errors that explain how to replace integer milliseconds with `datetime.timedelta`.

## Implementation

```python
# Before
await ctx.step.sleep("delay", 5000)
inngest.RateLimit(limit=5, period=60000)
inngest.TriggerCron(cron="*/5 * * * *", jitter="30s")

# After
await ctx.step.sleep("delay", datetime.timedelta(seconds=5))
inngest.RateLimit(limit=5, period=datetime.timedelta(minutes=1))
inngest.TriggerCron(
    cron="*/5 * * * *",
    jitter=datetime.timedelta(seconds=30),
)
```

### Affected public fields

- `Batch.timeout`
- `Cancel.timeout`
- `Debounce.period`
- `Debounce.timeout`
- `RateLimit.period`
- `Throttle.period`
- `Timeouts.start`
- `Timeouts.finish`
- `TriggerCron.jitter`
- `Inngest(request_timeout=...)`
- `RetryAfterError(retry_after=...)`, while still allowing absolute `datetime.datetime`
- `Step.sleep(...)` and `StepSync.sleep(...)`
- `Step.wait_for_event(..., timeout=...)` and `StepSync.wait_for_event(..., timeout=...)`
- `Step.invoke(..., timeout=...)` and `StepSync.invoke(..., timeout=...)`
- `Step.invoke_by_id(..., timeout=...)` and `StepSync.invoke_by_id(..., timeout=...)`

`TriggerCron.cron` remains a string because cron syntax is inherently string-based. Expression strings such as `Cancel.if_exp`, `Debounce.key`, and similar fields are not in scope just because they are strings.

### Runtime rejection

Affected public APIs must reject `int` values at the public boundary. Do not silently reinterpret integers as seconds or preserve the old millisecond behavior.

This applies to ordinary methods and constructors, not only type annotations or registration serialization. Existing branches like `isinstance(value, int)` in `Step.sleep`, `RetryAfterError`, and `Inngest(request_timeout=...)` must become explicit rejection paths.

Reject `bool` anywhere integers are rejected. In Python, `bool` is an `int` subclass, so checks must avoid accepting `True` or `False` as durations.

Errors should be migration-friendly but do not need to be tailored to every callsite. Use one reusable message shape that names the affected parameter when available:

```text
Integer durations are no longer accepted for <parameter>. Use datetime.timedelta instead.
```

### Internal duration helpers

`_internal.transforms.to_duration_str()` should accept only `datetime.timedelta`. `_internal.transforms.to_maybe_duration_str()` should accept only `datetime.timedelta | None`. Both helpers should reject integers.

Public serializers and step methods should rely on these strict helpers so integer rejection is consistent across config models and step APIs. If an internal path truly needs millisecond integers, it should use a separate helper with an explicit name rather than the generic duration serializer.

`RetryAfterError(retry_after=...)` still allows absolute `datetime.datetime`, but that should use retry-after timestamp conversion rather than the duration-string helpers.

### Precision and validity

Registration and step scheduling durations must be positive whole-second `datetime.timedelta` values. Reject zero, negative, and sub-second values.

Whole-second validation must be exact: `timedelta.total_seconds()` must be greater than zero and integral, with no rounding. For example, `datetime.timedelta(seconds=1)` is valid, but `datetime.timedelta(milliseconds=999)`, `datetime.timedelta(seconds=1, microseconds=1)`, `datetime.timedelta(0)`, and negative durations are invalid.

This rule applies to:

- `Batch.timeout`
- `Cancel.timeout`
- `Debounce.period`
- `Debounce.timeout`
- `RateLimit.period`
- `Throttle.period`
- `Timeouts.start`
- `Timeouts.finish`
- `TriggerCron.jitter`
- `Step.sleep(...)` and `StepSync.sleep(...)`
- `Step.wait_for_event(..., timeout=...)` and `StepSync.wait_for_event(..., timeout=...)`
- `Step.invoke(..., timeout=...)` and `StepSync.invoke(..., timeout=...)`
- `Step.invoke_by_id(..., timeout=...)` and `StepSync.invoke_by_id(..., timeout=...)`

`Inngest(request_timeout=...)` and `RetryAfterError(retry_after=datetime.timedelta(...))` may use positive sub-second durations because they map to local HTTP timeout and retry-after timestamp behavior. They must still reject zero and negative durations.

`RetryAfterError(retry_after=datetime.datetime(...))` must receive an absolute future timestamp.

### Tests

Add coverage for:

- Every affected Pydantic/config model field accepts valid `datetime.timedelta` values.
- Every affected Pydantic/config model field rejects `int` and `bool`.
- Direct step methods reject `int` and `bool`, including `sleep`, `wait_for_event`, `invoke`, and `invoke_by_id`.
- `Inngest(request_timeout=...)` rejects `int`, `bool`, zero, and negative durations while accepting positive sub-second `datetime.timedelta` values.
- `RetryAfterError(retry_after=...)` rejects `int`, `bool`, zero and negative timedeltas, and past datetimes while accepting positive sub-second timedeltas and future datetimes.
- Registration and step scheduling durations reject zero, negative, and sub-second timedeltas with no rounding.
- `_internal.transforms.to_duration_str()` rejects `int`, `bool`, `None`, zero, negative, and sub-second values.
- `_internal.transforms.to_maybe_duration_str()` rejects `int`, `bool`, zero, negative, and sub-second values while accepting `None`.
- Error messages use the reusable migration-friendly shape and include the parameter name when available.
