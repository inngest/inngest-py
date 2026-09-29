# Deferred: invoke replay validates unused sessions

`step.invoke()` and `step.invoke_by_id()` validate sessions before checking for a saved result. If `ctx.sessions` or explicit `meta` becomes invalid on replay, the parent fails despite the child already completing. Valid, deterministic metadata is unaffected.

## Reproduction

1. Invoke a child with `meta={"sessions": {"conversation": "chat-1"}}`.
2. After the child completes, have a later step fail and retry.
3. On that retry, pass an empty conversation ID to the same invoke step.

Expected: return the saved result. Actual: validation fails. Reproduced against a real server with sync and async handlers.

`step.send_event()` is already fixed: validation runs inside its durable callback, which replay skips.

## Future fix

In `pkg/inngest/inngest/_internal/step_lib/{step_async,step_sync}.py`, defer invoke payload construction until after replay is resolved. Keep internal interfaces simple.

Add a real-server test asserting that the parent completes and the child runs once. Verify sync, async, and parallel invokes, including saved results and errors.
