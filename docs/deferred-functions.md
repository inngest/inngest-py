# Deferred functions

Deferred functions run independent work after the parent run finishes. They have their own retries and steps. The parent does not wait for their results.

```python
import inngest
from inngest.experimental import create_defer

client = inngest.Inngest(app_id="example")


@create_defer(client, fn_id="record-feedback", retries=3)
async def record_feedback(ctx: inngest.Context) -> None:
    parent = ctx.parents[0]
    ctx.logger.info(f"Feedback for run {parent.run_id}: {ctx.event.data}")


@client.create_function(
    fn_id="answer",
    trigger=inngest.TriggerEvent(event="question/received"),
)
async def answer(ctx: inngest.Context) -> str:
    ctx.defer("feedback", function=record_feedback, data={"answer": "Hello"})
    return "Hello"
```

Register both functions with your serving adapter. Sync handlers use `ContextSync`; `ctx.defer()` and its returned handle's `abort()` are synchronous in both kinds of handler. Defer calls also work inside `step.run()`.

Defer IDs must be unique within a run. Replays do not schedule previously accepted IDs again. Duplicate calls in one execution are logged and skipped.

Inputs must be JSON-serializable dictionaries. The SDK snapshots them at the call site. Invalid targets, IDs, input data, or session metadata are logged and skipped instead of failing the parent. A skipped call returns a harmless abort handle. Deferred-handler failures affect the deferred run, not the parent.

**Encryption limitation:** `ctx.defer()` sends input in plaintext even when `EncryptionMiddleware` is configured, including fields normally protected by that middleware. Do not pass data that relies on middleware encryption to deferred functions yet.

TODO: Apply configured encryption to deferred input before sending it, with coverage for encrypted outgoing data and decrypted child input.

Call `handle.abort()` in the parent handler to cancel a scheduled defer. Inside a step callback, you can also cancel a defer newly scheduled in that same callback: replay skips both calls. Cancelling a defer created outside the current callback is logged and skipped; return the cancellation decision from the step and call `abort()` afterward. Repeated aborts are harmless. Once the server marks the defer as no longer abortable, abort does nothing.

Scheduling and cancellation are buffered until the next step or successful completion response. If the parent fails before that response, including by returning unserializable output, buffered operations are logged and discarded. Previously accepted children still run, and previously accepted children with discarded cancellations remain scheduled. The parent's error and retry policy are preserved. This is a current Python SDK limitation. To ensure a schedule or cancellation reaches the server before later work can fail, complete a step after making the call.

TODO: Send buffered defers on parent failure without causing an extra parent execution or changing retry behavior. TypeScript sends them alongside `StepError` or `StepFailed`, but that approach caused extra parent executions in the Python integration test. TypeScript's corresponding test checks child delivery, not the number of parent executions.

Deferred runs inherit `ctx.sessions`. Use `meta.sessions` for explicit overrides or removals, as with event sends. Pass `experiment=selected.experiment_ref` to carry an experiment assignment to the deferred handler; this does not write scores automatically.

Handlers receive clean input in `ctx.event.data` and parent information in `ctx.parents`, aligned with `ctx.events`. Each parent contains `fn_slug`, `run_id`, and an optional `experiment`. Internal routing fields are removed before input middleware runs.

Deferred functions have an implicit trigger. Custom triggers, batching, and `on_failure` handlers are not supported. This API is experimental.
