# Sequential checkpointing (opt-in MVP)

Checkpointing allows sequential steps to complete in one HTTP invocation.
Each result is acknowledged by the Inngest checkpoint API before execution
continues. The existing server owns persistence, scheduling and retries.

    import datetime
    import inngest

    client = inngest.Inngest(
        app_id="example",
        checkpointing=inngest.Checkpointing(
            max_runtime=datetime.timedelta(seconds=50),
        ),
    )

    @client.create_function(
        fn_id="example",
        trigger=inngest.TriggerEvent(event="example/requested"),
    )
    def example(ctx: inngest.ContextSync) -> int:
        first = ctx.step.run("first", lambda: 1)
        return ctx.step.run("second", lambda: first + 1)

Async handlers and async step callbacks are also supported. Client configuration
defaults to disabled. A function's checkpointing=None inherits the client
setting; False disables it, True enables it without a runtime limit, and a
Checkpointing instance overrides the runtime budget.

Choose a runtime budget below the HTTP server/platform timeout, with enough
headroom for a running step and response delivery. The budget is cooperative:
it can yield between steps, but cannot interrupt an arbitrary Python callback.
An expired invocation plans its next step through ordinary orchestration, or
returns the most recently completed, uncheckpointed step normally.

## Safety and compatibility

- Default behavior is unchanged. Old requests without fn_id/qi_id use ordinary
  execution. An unavailable checkpoint endpoint returns the completed step
  through the ordinary 206 response.
- Retry invocations (attempt > 0), targeted step requests, disabled immediate
  execution and Connect use ordinary execution. In particular, the tested server
  can retain a previous attempt count in its active executor even after a
  checkpoint resets the stored queue item. Yielding retried steps avoids spending
  the next step's retry allowance.
- Parallel discovery, sleeps, waits, invocations and gateway operations retain
  executor scheduling. A subsequent eligible invocation may checkpoint again.
- Pending deferred operations yield with the completed step so both reach the
  executor together; a persisted callback must not lose its deferred work on replay.
- This is the executor-initiated checkpoint protocol. It does not implement
  durable HTTP endpoints, local parallel scheduling, buffering or timer flushes.
- Checkpoints use the configured API origin, environment header and hashed
  signing-key authentication. Key fallback is sticky within an invocation.
  Transient failures get at most three attempts, each using the same result and
  step identity; permanent HTTP failures fall back immediately.
- Step effects remain **at least once**. A crash before persistence may repeat
  the callback. Use idempotency for external effects.
- The checkpointer creates no background tasks or flush threads. Async
  cancellation propagates without scheduling another step or retry, but an
  in-flight HTTP write may still commit (including when the shared HTTP client
  uses a thread). Sync callbacks retain their framework's existing cancellation
  limitations.

Output middleware runs before each checkpoint. After acknowledgement, input
middleware receives the newly persisted memo before the result is returned to
user code. This preserves encryption and output transformation on both fresh
execution and replay. Custom input middleware must therefore support repeated
calls during an invocation; it receives only the new memo on these calls.
Execution/response lifecycle hooks retain invocation scope. Checkpoint fallback
does not transform the same output a second time.

The real-server tests use Inngest v1.45.1. Other server versions and Inngest
Cloud still need their own compatibility verification.

## Tests

Run normal package checks from pkg/inngest:

    make utest
    make lint
    make type-check

From the SDK repository root, against a separately running local server:

    inngest dev --no-discovery --no-poll --port 8399 --retry-interval 1

    DEV_SERVER_ENABLED=0 DEV_SERVER_PORT=8399 INNGEST_DEV=http://127.0.0.1:8399 uv run pytest tests/test_inngest/test_checkpointing.py -q

This exercises sync/async execution, lost acknowledgements, checkpoint outages,
waits, parallel branches, per-step retry budgets, runtime yielding, encryption,
function failure after persistence, and actual worker termination/restart on
both sides of the persistence boundary. Faults and test effects are synthetic.

The optional Hypothesis suite is deliberately named outside pytest's default
test-file patterns and adds no runtime or CI dependency:

    CHECKPOINT_PROPERTY_EXAMPLES=1000 uv run --with hypothesis==6.168.1 --with pytest==9.0.3 pytest tools/checkpoint_properties.py -q --hypothesis-show-statistics

It generates nested JSON values, repeated step names, transport failure
sequences, lost worker responses and reversible middleware transformations.
An independent durable-storage model checks bounded completion, matching
outputs, distinct step identities and no re-execution of persisted callbacks.
It runs each property for sync and async handlers. Hypothesis keeps/shrinks
failing examples in its local database; a failure should become a focused
regression case before fixing the implementation. See the
[Hypothesis documentation](https://hypothesis.readthedocs.io/en/latest/reference/api.html).
