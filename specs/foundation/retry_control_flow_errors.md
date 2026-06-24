# Retry control-flow errors become step interrupts

Area: Execution
Change type: Correctness

## Problem

`RetryAfterError` and `NonRetriableError` currently inherit from the SDK's `Error` base class, which inherits from `Exception`. That inheritance is correct for the public error API, but `step.run` currently re-raises these errors from the step callback.

When user code wraps `ctx.step.run(...)` in a broad `except Exception`, that broad handler can catch the original retry-control error on the same request.

This is clearly incorrect for `RetryAfterError`: user code can accidentally turn a requested step retry into a successful function return. `NonRetriableError` is less likely to produce an incorrect retry schedule, but it has the same inconsistent control-flow shape. Step callback errors should be owned by the step execution protocol, and user code around `step.run` should only observe a memoized `StepError` after the function re-enters.

## Solution

Keep `RetryAfterError` and `NonRetriableError` as normal `Exception` subclasses. Do not move them to `BaseException`.

Instead, change `step.run` callback handling. When a step callback raises `RetryAfterError` or `NonRetriableError`, `step.run` should convert that callback failure into the existing SDK `ResponseInterrupt`, which already inherits from `BaseException`. The caller's broad `except Exception` around `ctx.step.run(...)` will not catch `ResponseInterrupt`, so the SDK can return the correct step-level response.

For `step.run`, both errors interrupt the current request and are converted into step responses. User code surrounding `step.run` only sees an exception when the Executor later sends the SDK a memoized step error, at which point `step.run` raises `inngest.StepError`.

Function-level raises remain unchanged. If the function handler raises `RetryAfterError` or `NonRetriableError` outside a step callback, the SDK returns a function-level error response.

## Out of scope

This does not change the public error hierarchy, wire protocol, retry policy configuration, `StepError` shape, or how ordinary user exceptions raised inside a step are represented after memoization.

This does not prevent user code inside the step callback from catching `RetryAfterError` or `NonRetriableError` with `except Exception`. The bug addressed here is broad exception handling around `ctx.step.run(...)`.

## Risks

The main risk is converting at the wrong boundary. If `step.run` re-raises the original `Exception`, user code can still catch it. If the SDK converts it to `ResponseInterrupt` too late, the function may return a normal response. If response serialization misses the step-level metadata, the Executor may retry at the wrong time or retry a non-retryable failure.

## Implementation

Keep the public error hierarchy unchanged:

```python
class Error(Exception):
    ...


class NonRetriableError(Error):
    ...


class RetryAfterError(Error):
    ...
```

Do not add `RetryControlFlowError`, `to_exception()`, or any new public catch target for this change.

The failure mode today:

```python
def do_work() -> None:
    raise inngest.RetryAfterError("try later", datetime.timedelta(seconds=1))


def handler(ctx: inngest.ContextSync) -> str:
    try:
        ctx.step.run("do-work", do_work)
    except Exception:
        return "failed"
    return "completed"
```

Today, `step.run` can re-raise the callback's original `RetryAfterError`. The broad `except Exception` catches it, so the function returns `"failed"` on the first request instead of scheduling the step retry.

### Step callback boundary

Update async and sync `step.run` callback handling. The current branch that catches `RetryAfterError` and `NonRetriableError` and re-raises them to the function level is the bug.

Instead:

- Catch `RetryAfterError` from the step callback.
- Set the step opcode to `STEP_ERROR`.
- Raise `ResponseInterrupt(StepResponse(original_error=err, step=step_info))`.
- Catch `NonRetriableError` from the step callback.
- Set the step opcode to `STEP_FAILED`.
- Raise `ResponseInterrupt(StepResponse(original_error=err, step=step_info))`.

This keeps the original concrete error object available to SDK response serialization and middleware, while ensuring user code around `ctx.step.run(...)` sees only the `ResponseInterrupt` control flow.

Do not convert these errors to another exception type. Middleware and response serialization should continue to see the original `RetryAfterError` or `NonRetriableError` object.

### Wire response scope

Retry-control errors use the response scope where they are raised.

If `RetryAfterError` is raised inside a `step.run` callback, return a step-level response using the existing step-error wire shape and set the response-level `Retry-After` header.

If `RetryAfterError` is raised outside a step callback, return a function-level error response and set the response-level `Retry-After` header.

If `NonRetriableError` is raised inside a `step.run` callback, return a step-level non-retryable failure response and set `X-Inngest-No-Retry: true`.

If `NonRetriableError` is raised outside a step callback, return a function-level non-retryable error response and set `X-Inngest-No-Retry: true`.

The current Python behavior that bubbles retry-control errors from a step callback to function-level response construction is a bug. Step callback retry-control errors must remain step-level responses.

### Step opcode semantics

Ordinary step callback exceptions keep the existing opcode behavior:

- Use `STEP_ERROR` while step retries remain.
- Use `STEP_FAILED` on the final step attempt.

Step-level `RetryAfterError` should use `STEP_ERROR` and set the response-level `Retry-After` header. The retry-after timestamp changes scheduling of the next step attempt; it does not make the step permanently failed.

Step-level `NonRetriableError` should use `STEP_FAILED` immediately and set `X-Inngest-No-Retry: true`. Do not emit `STEP_ERROR` plus a no-retry header for this case.

### Response serialization

Because the public errors remain `Exception` subclasses, ordinary SDK error carriers should not need to widen to `BaseException`.

Response serialization must preserve retry-control metadata:

- `RetryAfterError` still carries the absolute retry-after timestamp used for `Retry-After`.
- `NonRetriableError` remains non-retryable.
- Both preserve `message`, `name`, `stack` behavior, and `quiet` handling.

The step response aggregation path must preserve `StepResponse.original_error` through `CallResult.from_responses`. `CommResponse.from_call_result` must set response-level headers from step-level errors inside `CallResult.multi`, including `Retry-After` for `RetryAfterError` and `X-Inngest-No-Retry: true` for `NonRetriableError`.

### Middleware behavior

Middleware that observes step errors should receive the original concrete error object:

- `RetryAfterError` for retry-after step errors.
- `NonRetriableError` for non-retryable step failures.
- Ordinary exception objects for ordinary step failures.

This keeps middleware behavior intuitive: if user code raises `RetryAfterError`, middleware sees `RetryAfterError`, not a converted internal wrapper.

`ResponseInterrupt` remains internal SDK control flow. Public middleware hooks should not receive `ResponseInterrupt` as an error payload or need to handle it directly.

Middleware may replace step callback errors before response serialization. Replacement can go both directions:

- An ordinary exception can be replaced with `RetryAfterError` or `NonRetriableError`, causing retry-control response metadata to be applied.
- `RetryAfterError` or `NonRetriableError` can be replaced with an ordinary exception, causing ordinary step-error response behavior.

If middleware replaces the error, response serialization should respect the replacement error's retry metadata or lack of retry metadata. If middleware preserves the error, retry-after, non-retryable, `quiet`, message, name, and stack metadata must remain intact.

### Tests

Add regression tests for the userland failure mode:

- Sync `step.run` callback raises `RetryAfterError` while caller wraps `ctx.step.run(...)` in `except Exception`.
- Async `step.run` callback raises `RetryAfterError` while caller wraps `await ctx.step.run(...)` in `except Exception`.
- In both retry-after cases, the broad `except Exception` branch is not reached, the function does not return a normal success response, and the response is step-level with `206`, `STEP_ERROR`, and `Retry-After`.
- Sync `step.run` callback raises `NonRetriableError` while caller wraps `ctx.step.run(...)` in `except Exception`.
- Async `step.run` callback raises `NonRetriableError` while caller wraps `await ctx.step.run(...)` in `except Exception`.
- In both non-retriable cases, the broad `except Exception` branch is not reached, the function does not return a normal success response, and the response is step-level with `206`, `STEP_FAILED`, and `X-Inngest-No-Retry: true`.

Add function-level regression tests:

- Sync and async function handlers that raise `RetryAfterError` outside a step remain function-level error responses with `Retry-After`.
- Sync and async function handlers that raise `NonRetriableError` outside a step remain function-level non-retryable error responses with `X-Inngest-No-Retry: true`.
- Existing `quiet` behavior is preserved.

Add response-level and middleware tests:

- `on_step_error` sees the original concrete `RetryAfterError` or `NonRetriableError` object for step callback failures.
- `wrap_step_handler` cleanup still runs when the step callback exits through retry-control errors.
- Middleware can replace an ordinary step callback exception with `RetryAfterError`, and the response becomes step-level `STEP_ERROR` with `Retry-After`.
- Middleware can replace an ordinary step callback exception with `NonRetriableError`, and the response becomes step-level `STEP_FAILED` with `X-Inngest-No-Retry: true`.
- Middleware can replace `RetryAfterError` with an ordinary exception, and the response uses ordinary step-error retry behavior without `Retry-After`.
- Middleware can replace `NonRetriableError` with an ordinary exception, and the response uses ordinary step-error retry behavior without `X-Inngest-No-Retry`.
- Retry-after metadata survives middleware when middleware preserves the original error.
- Non-retryable metadata survives middleware when middleware preserves the original error.
- `CallResult.from_responses` and `CommResponse.from_call_result` preserve retry-control metadata from `StepResponse.original_error`.
- Step-level `RetryAfterError` in the step response aggregation path sets `Retry-After`.
- Step-level `NonRetriableError` in the step response aggregation path sets `X-Inngest-No-Retry: true`.
