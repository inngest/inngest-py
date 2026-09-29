# Deferred functions

Deferred functions run independent work after the parent run finishes, including when the parent fails. They have their own retries and steps. The parent does not wait for their results.

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

Call `handle.abort()` during the parent execution to cancel a scheduled defer. Repeated aborts are harmless. Once the server marks the defer as no longer abortable, abort does nothing.

Deferred runs inherit `ctx.sessions`. Use `meta.sessions` for explicit overrides or removals, as with event sends. Pass `experiment=selected.experiment_ref` to carry an experiment assignment to the deferred handler; this does not write scores automatically.

Handlers receive clean input in `ctx.event.data` and parent information in `ctx.parents`, aligned with `ctx.events`. Each parent contains `fn_slug`, `run_id`, and an optional `experiment`. Internal routing fields are removed before input middleware runs.

Deferred functions have an implicit trigger. Custom triggers, batching, and `on_failure` handlers are not supported. This API is experimental.
