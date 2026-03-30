# Execution Model

How the SDK executes functions and steps using deterministic replay.

## Core Concept: Replay

An Inngest function is called **multiple times per run**, once for each step (or group of parallel steps) that needs to execute. Each call replays the user's function from the top. Previously-completed steps return their memoized results instantly; the first unmemoized step either executes or gets planned.

Deterministic function code (same steps in the same order on every replay) is ideal, but the SDK makes a best effort to handle non-determinism. If a new step appears that has no memo, it runs. If a memoized step is no longer encountered, its memo is ignored. The one case that currently produces an error is when step targeting is active and the targeted step is not found during replay.

### Example

```python
@client.create_function(
    fn_id="my-fn",
    trigger=inngest.TriggerEvent(event="app/signup"),
)
async def my_fn(ctx: inngest.Context) -> str:
    user = await ctx.step.run("create-user", create_user)       # Step A
    await ctx.step.run("send-email", lambda: send_email(user))  # Step B
    return "done"
```

This function will be called **3 times** for a complete run:

| Request # | Memos                    | What happens                                                                                                   |
| --------- | ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| 1         | `{}`                     | Step A has no memo → executes `create_user`. Returns step A's output to the Executor. Step B is never reached. |
| 2         | `{A: result}`            | Step A has a memo → returns instantly. Step B has no memo → executes `send_email`. Returns step B's output.    |
| 3         | `{A: result, B: result}` | Both steps return from memo. Function body completes and returns `"done"`.                                     |

## Key Components

### StepMemos

`StepMemos` (`_internal/step_lib/base.py`) holds memoized outputs from the `ServerRequest`. Each memo is keyed by a hashed step ID and contains either `data` (success) or `error` (failure). Memos are consumed via `pop()`; once a memo is popped, it's removed. When `size` reaches 0, all remaining code is new (unmemoized).

### ExecutionV0

`ExecutionV0` (`_internal/execution_lib/v0.py`) is the replay engine. It has two methods:

**`run()`** wraps the user function call. Catches three types of exceptions:

- `ResponseInterrupt` → steps were planned or executed; convert to `CallResult`
- `UserError` → the user's code raised an exception
- `SkipInterrupt` → non-determinism detected during step targeting

**`report_step(step_info)`** is called by every step method. This is where the replay logic lives:

```
1. Pop memo for this step's hashed ID
2. If memo exists:
   → Return memoized data/error (step is "replayed")
3. If no memo (step is new):
   a. If step targeting is enabled and this isn't the target → raise SkipInterrupt
   b. If in parallel mode → change opcode to PLANNED, raise ResponseInterrupt
   c. If disable_immediate_execution is set → change opcode to PLANNED, raise ResponseInterrupt
   d. If opcode is STEP_RUN → return (let the step execute its handler)
   e. Otherwise (SLEEP, WAIT_FOR_EVENT, INVOKE, etc.) → raise ResponseInterrupt
```

The distinction in (d) vs (e): `step.run()` is the only step type that executes user code in the SDK. All other step types (sleep, wait_for_event, invoke) just tell the Executor what to do. The Executor handles the actual waiting/invocation. Note that `step.send_event()` is implemented as a `step.run()` under the hood, so the event is sent SDK-side.

### Step Methods

Each step method (`_internal/step_lib/step_async.py`) follows the same pattern:

1. Parse the step ID (hash it, handle deduplication for reused IDs)
2. Build a `StepInfo` with the appropriate opcode
3. Call `execution.report_step(step_info)`, which either returns memoized data or raises an interrupt
4. If memoized: return the data (or raise the error)
5. If not memoized and this is `step.run()`: execute the handler, then raise a `ResponseInterrupt` with the output

The `report_step` → `ReportedStep` context manager pattern is how steps interact with the execution engine. `ReportedStep` implements `__aenter__`/`__aexit__` and also detects nested steps (which are not supported).

### step.run() Specifically

`step.run()` is unique because it's the only step that executes user-provided code:

```
report_step returns (no memo, not in parallel, is STEP_RUN)
  → enters the context manager body
  → calls the user's handler
  → on success: raises ResponseInterrupt with output + STEP_RUN opcode
  → on error: raises ResponseInterrupt with STEP_ERROR or STEP_FAILED opcode
```

`STEP_ERROR` means "this attempt failed but can be retried." `STEP_FAILED` means "all attempts exhausted." The SDK checks `attempt + 1 >= max_attempts` to decide which one.

## Parallel Execution

`Group.parallel()` (`_internal/step_lib/group.py`) enables running multiple steps concurrently on the Executor. It works through a **discovery phase**:

1. Set the `in_parallel` context variable to `True`
2. Call each callable sequentially
3. Each step calls `report_step()`, which sees `in_parallel=True` and:
   - If the step has a memo → return it (already completed)
   - If the step is new → change opcode to `PLANNED` and raise `ResponseInterrupt`
4. Collect all `ResponseInterrupt`s into a single list
5. If any new steps were discovered: raise one combined `ResponseInterrupt` with all planned steps
6. If all steps had memos: return all outputs (parallel group is fully replayed)

The Executor receives the list of planned steps and executes them concurrently, using **step targeting** (`stepId` query param) to tell the SDK which specific step to run on each subsequent request.

### Step Targeting

When the Executor wants to run a specific step from a parallel group, it sends `stepId=<hashed_id>` in the query params. During replay:

- Steps whose hashed ID matches the target execute normally
- Steps that don't match raise `SkipInterrupt`, which the execution engine handles
- This allows the Executor to run parallel steps concurrently across multiple requests

### disable_immediate_execution

After parallel steps complete, the next sequential `step.run()` encountered will have `disable_immediate_execution=True` in the request context. This forces the step to be planned rather than immediately executed, ensuring that a single step isn't executed multiple times for a single run.

## Interrupts as Control Flow

The SDK uses exceptions that extend `BaseException` (not `Exception`) for internal control flow:

| Interrupt             | Extends         | Purpose                                                                                  |
| --------------------- | --------------- | ---------------------------------------------------------------------------------------- |
| `ResponseInterrupt`   | `BaseException` | A step was planned or executed; carries the step response(s) back to `ExecutionV0.run()` |
| `SkipInterrupt`       | `BaseException` | Step targeting is active and this step isn't the target                                  |
| `NestedStepInterrupt` | `BaseException` | A step was called inside another step's handler (not supported)                          |

These extend `BaseException` rather than `Exception` so that user code with `except Exception` won't accidentally catch them. They are not errors. They are the mechanism by which steps communicate results back up the call stack to the execution engine.

## Middleware

Middleware hooks run at specific points during execution. Users can subclass `Middleware` (async) or `MiddlewareSync` to tap into these. The `MiddlewareManager` orchestrates multiple middleware in sequence.

See `_internal/middleware_lib/`.
