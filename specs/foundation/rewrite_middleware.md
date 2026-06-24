# Rewrite middleware

Area: Middleware
Change type: Architecture

## Problem

Python middleware has grown independently from the TypeScript SDK and does not yet have a complete v0.6 design. This creates drift across SDKs and makes cross-language behavior harder to document, test, and support.

## Solution

Rewrite middleware lifecycle hooks to mimic the TypeScript SDK v4 middleware model as much as possible, while preserving Python-specific ergonomics where needed.

The primary deliverable is hook lifecycle parity: the same conceptual phases should exist in Python and TypeScript, with the same ordering and error propagation semantics.

## Out of scope

This spec does not attempt to invent a Python-only middleware model or broaden middleware beyond lifecycle parity with TypeScript v4.

## Risks

Middleware is cross-cutting. A poorly specified rewrite can regress logging, serialization, tracing, event sending, step behavior, or error handling. This section should not be implemented until the open questions are resolved.

## Open questions

- The exact public argument and return types for every hook still need a final API pass before implementation.

## Implementation

This should be treated as a concrete v0.6 breaking change, not an open-ended middleware redesign.

Python-specific differences should be limited to language and runtime necessities such as sync vs async handlers, context managers, and typing.

This spec is related to [`foundation/context_ext.md`](./context_ext.md), which defines the dedicated namespace for middleware-provided application extensions.

This spec is related to [`foundation/payload_serializers.md`](./payload_serializers.md), which defines payload boundary transformation for serialization, encryption, and other reversible app/server data transforms.

### Implementation checklist

- Remove the old public middleware hook contract: `MiddlewareSync`, old hook names, and `TransformOutputResult`.
- Add the new public middleware API: `Middleware`, lifecycle hook argument types, wrapper argument types, notification argument types, and public exports.
- Replace duplicated sync and async middleware dispatch with centralized helpers for async maybe-await behavior and sync awaitable rejection.
- Wire function lifecycle hooks through `function.py` and `execution_lib/v0.py`, including `transform_function_input`, `on_run_start`, `on_memoization_end`, wrapper hooks, run completion, and run error.
- Wire step lifecycle hooks through `step_lib/step_async.py` and `step_lib/step_sync.py`, including `wrap_step`, `transform_step_input`, `wrap_step_handler`, `on_step_start`, `on_step_complete`, and `on_step_error`.
- Wire request boundary behavior through `comm_lib/handler.py`, including `wrap_request` and request-level cleanup.
- Replace send-side `skip_middleware` behavior in `client_lib/client.py` and step send paths with active send middleware scope selection.
- Add the `ContextVar`-backed active send scope for function-scoped sends.
- Migrate built-in middleware in the same SDK change: `LoggerMiddleware`, `RemoteStateMiddleware`, and `SentryMiddleware`.
- Preserve the staged `inngest_encryption` release plan described below.
- Update server timings, docs, examples, public exports, and tests so no old middleware hook remains in v0.6.

### Test plan

- Cover transform ordering: hooks run forward, each hook receives the current argument from prior middleware, replacement arguments flow to later middleware, in-place mutation is preserved, and returning `None` fails the operation.
- Cover wrapper ordering: wrappers use onion order, success values propagate outward, errors propagate outward, wrappers can replace outputs or errors where the lifecycle allows it, and `finally` cleanup runs in reverse order.
- Cover notification hooks: runtime notifications run forward, notification hook errors are logged without failing user execution, and `on_register` errors fail registration.
- Cover function lifecycle: `transform_function_input`, `on_run_start`, `on_memoization_end`, `wrap_function_handler`, `on_run_complete`, and `on_run_error` fire in the expected order for first attempts, memoized attempts, successful returns, user errors, and caught memoized `StepError`s.
- Cover internal response interrupts: step planning, sleeps, waits, sends, and scheduled retries do not fire `on_run_complete` or `on_run_error`.
- Cover step lifecycle: step callback execution fires `on_step_start`, `wrap_step_handler`, `on_step_complete`, and `on_step_error`; planned steps and memoized step replay do not fire step callback hooks; original callback exceptions are visible to `on_step_error`; memoized step errors replay to user code as `inngest.StepError`.
- Cover send lifecycle: direct `client.send(...)` uses client middleware only, function-scoped `client.send(...)` uses client plus function middleware exactly once, and `ctx.step.send_event(...)` uses the active function execution middleware stack exactly once.
- Cover active send scope isolation: background asyncio tasks created during function execution do not keep using function-scoped middleware after the function execution scope is inactive, and sends from another thread fall back to client middleware.
- Cover sync and async behavior: async execution accepts sync and async middleware, sync execution accepts sync middleware, and sync execution rejects coroutine hooks or awaitable hook results with the documented error.
- Cover migrated built-in middleware: idempotent logger behavior, remote-state load/save behavior, Sentry tagging/capture/flush behavior, and `inngest_encryption` v0.6 behavior after its staged compatibility release.
- Cover serializer interaction: ordinary middleware sees application-level values where documented, serializer boundary transforms run in the order defined by [`foundation/payload_serializers.md`](./payload_serializers.md), and encrypted wire envelopes do not leak into ordinary middleware unless a specific boundary explicitly documents that behavior.

### TypeScript parity target

The goal is to re-implement the TypeScript SDK v4 middleware model as much as Python reasonably allows. Python's static type system and sync/async runtime model will require some differences, but those differences should be intentional, documented, and limited.

Key TypeScript references:

- [TypeScript middleware lifecycle docs](https://www.inngest.com/docs/reference/typescript/v4/middleware/lifecycle)
- [TypeScript middleware source](https://github.com/inngest/inngest-js/blob/main/packages/inngest/src/components/middleware/middleware.ts)

Python should mirror the TypeScript middleware lifecycle concepts:

- `on_register`
- `on_memoization_end`
- `on_run_start`
- `on_run_complete`
- `on_run_error`
- `on_step_start`
- `on_step_complete`
- `on_step_error`
- `transform_function_input`
- `transform_send_event`
- `transform_step_input`
- `wrap_function_handler`
- `wrap_request`
- `wrap_send_event`
- `wrap_step`
- `wrap_step_handler`

### Current hook migration map

Each current Python hook needs a clear migration target:

| Current Python hook | v0.6 target |
| --- | --- |
| `before_execution` | Split across `on_run_start`, `on_memoization_end`, `on_step_start`, and wrapper hooks depending on the use case. Run-level setup should move to `on_run_start` or `wrap_function_handler`; step-attempt setup should move to `on_step_start` or `wrap_step_handler`. |
| `after_execution` | Replace with `on_run_complete`, `on_run_error`, or `wrap_function_handler` cleanup depending on whether the middleware needs success-only, error-only, or finally-style behavior. |
| `before_response` | Replace with `wrap_request` for response-level behavior. |
| `before_send_events` | Replace with `transform_send_event` for event mutation before send. Payload encoding belongs to serializers. |
| `after_send_events` | Replace with `wrap_send_event` for observing send success, failure, retries, and cleanup. |
| `transform_input` | Replace with `transform_function_input`. |
| `transform_output` | Replace with `wrap_function_handler` for function output/error transformation and `wrap_step_handler` for step-attempt output/error transformation. Do not keep in-place `TransformOutputResult` mutation in v0.6. |

Remove the old middleware hook contract completely in v0.6. Do not keep deprecated compatibility shims for `before_execution`, `after_execution`, `before_response`, `before_send_events`, `after_send_events`, `transform_input`, `transform_output`, `MiddlewareSync`, or `TransformOutputResult`. The public `Middleware` symbol may remain, but it exposes only the new TypeScript-aligned lifecycle API.

### Ordering and error propagation

Follow the TypeScript SDK ordering model.

### Payload serializer interaction

Middleware should not own serialization, encryption, or other app/server payload boundary transforms. Those concerns belong to the payload serializer pipeline defined in [`foundation/payload_serializers.md`](./payload_serializers.md).

The practical rule is:

- Serializers transform payload values crossing the app/server boundary.
- Middleware observes, wraps, or mutates execution lifecycle behavior.
- Ordinary middleware should generally see application-level values, not encrypted wire envelopes.
- Inbound payloads should be decoded before function handlers and ordinary application middleware observe them.
- Outbound function and step outputs should pass through ordinary application middleware before payload serialization.

Middleware hooks may still mutate values that later pass through serializers. For example, `wrap_function_handler` and `wrap_step_handler` can replace raw application outputs; the final output is encoded by serializers after middleware finishes. `transform_function_input` can modify decoded `ctx.event`, `ctx.events`, and memoized step data before user code observes them.

Send-side event middleware has a special object-shaped event-data constraint. Send event preparation should follow the serializer ordering rules in [`foundation/payload_serializers.md`](./payload_serializers.md): normalize produced events, apply serializers needed to produce object-shaped event data, run ordinary `transform_send_event` middleware, validate object-shaped event data again, then apply outer wire serializers such as encryption before sending.

### Transform mutation contract

Python transform hooks may mutate the supplied operation argument in place and return that same argument, or they may return a replacement argument object. This differs from the TypeScript SDK's "do not mutate arguments" convention because mutable operation objects are idiomatic Python and produce better middleware ergonomics.

Transform hooks still run deterministically in registration order. Each hook receives the current argument object after all prior middleware mutations and replacements:

```python
class DbMiddleware(inngest.Middleware):
    def transform_function_input(
        self,
        arg: inngest.TransformFunctionInputArgs,
    ) -> inngest.TransformFunctionInputArgs:
        arg.ctx.ext.db = self.db
        return arg
```

Returning `None` from a transform hook is invalid. A transform that mutates in place must still return the argument object so the chain has one explicit current value.

Transform arguments must be SDK-owned, operation-scoped objects. Middleware mutation must not mutate caller-owned send inputs, raw request payloads, registration objects, or other state shared across operations.

Function input middleware can mutate `arg.ctx`, including `arg.ctx.event`, `arg.ctx.events`, and `arg.ctx.ext`. `ctx.ext` is the preferred place for application-specific additions:

```python
arg.ctx.ext.db = db
arg.ctx.ext.flags = flags
setattr(arg.ctx.ext, "tenant_id", tenant_id)
return arg
```

`ctx.ext` itself is SDK-owned and should not be replaced by middleware. Middleware should mutate attributes on the `ExtensionNamespace` described in [`foundation/context_ext.md`](./context_ext.md).

Do not use `ctx.ext` for SDK-owned fields such as events, step helpers, loggers, run IDs, or attempt metadata. SDK-owned fields may be mutated only when the transform argument exposes them for that hook and the mutation is scoped to the current operation.

### Hook payload types

Middleware hooks should receive one public argument object. Argument objects should be small SDK-owned mutable classes, preferably dataclasses or equivalent plain Python classes, not Pydantic models. These are public middleware APIs and should not expose internal model-copy helpers, executor internals, or framework-specific request objects as the only way to inspect state.

Info objects are read-only by convention. Transform argument objects are mutable. Wrapper argument objects carry a `next` callable plus the operation metadata. Notification argument objects are observational and should not be used for transformation.

Shared public payloads:

```python
@dataclasses.dataclass(frozen=True)
class MiddlewareRequestInfo:
    raw_request: object
    method: str | None = None
    url: str | None = None
    headers: typing.Mapping[str, str] | None = None


@dataclasses.dataclass(frozen=True)
class MiddlewareFunctionInfo:
    id: str
    name: str | None


@dataclasses.dataclass(frozen=True)
class MiddlewareStepInfo:
    id: str
    name: str | None
    op: str


@dataclasses.dataclass
class MiddlewareStepMemo:
    id: str
    op: str
    data: object
    error: inngest.StepError | None = None
```

`raw_request` preserves access to the framework-specific request when needed. Normalized `method`, `url`, and `headers` should be populated when the adapter can do so cheaply and consistently.

`MiddlewareFunctionInfo` and `MiddlewareStepInfo` should be stable public descriptions, not direct references to mutable internal registration or execution objects. If later specs need more fields, add them deliberately.

`MiddlewareStepMemo.data` is mutable so middleware such as encryption can decrypt memoized step data before the function handler observes it. Memoized step failures should be represented as `inngest.StepError`, not the original arbitrary exception, because memoized errors are received from the executor.

Transform hook arguments:

```python
@dataclasses.dataclass
class TransformFunctionInputArgs:
    request: MiddlewareRequestInfo
    function: MiddlewareFunctionInfo
    ctx: inngest.Context | inngest.ContextSync
    steps: typing.MutableMapping[str, MiddlewareStepMemo]


@dataclasses.dataclass
class TransformSendEventArgs:
    request: MiddlewareRequestInfo | None
    function: MiddlewareFunctionInfo | None
    step: MiddlewareStepInfo | None
    events: list[inngest.Event]


@dataclasses.dataclass
class TransformStepInputArgs:
    request: MiddlewareRequestInfo
    function: MiddlewareFunctionInfo
    ctx: inngest.Context | inngest.ContextSync
    step: MiddlewareStepInfo
    input: object
    options: dict[str, object]
```

`TransformSendEventArgs` uses optional `function` and `step` because client-level sends and function/step sends do not have the same scope. The exact scope rules are owned by the send-side behavior section.

Notification hook arguments should reuse the same shared payloads and expose only the event being observed:

```python
@dataclasses.dataclass(frozen=True)
class RunErrorArgs:
    request: MiddlewareRequestInfo
    function: MiddlewareFunctionInfo
    ctx: inngest.Context | inngest.ContextSync
    error: Exception


@dataclasses.dataclass(frozen=True)
class StepErrorArgs:
    request: MiddlewareRequestInfo
    function: MiddlewareFunctionInfo
    ctx: inngest.Context | inngest.ContextSync
    step: MiddlewareStepInfo
    error: Exception
```

Equivalent start, complete, and memoization hooks should follow the same shape and use `output: object` for successful outputs.

Wrapper hook arguments should expose the same metadata plus a `next` callable. The async and sync variants may use different callable types, but both should keep the same payload fields:

```python
@dataclasses.dataclass
class WrapFunctionHandlerArgs:
    request: MiddlewareRequestInfo
    function: MiddlewareFunctionInfo
    ctx: inngest.Context | inngest.ContextSync
    next: typing.Callable[[], object]
```

Public middleware error fields should be typed as `Exception`, not `BaseException`. Internal executor interrupts such as response-control exceptions must remain internal and should not appear in public middleware payloads. The SDK should catch middleware hook failures with `except Exception`, not broad `except BaseException`, unless a later implementation detail explicitly needs to rethrow an internal interrupt.

Middleware should not need to know about `ResponseInterrupt` or other internal `BaseException` control-flow values. Public middleware hooks should observe user-visible values, user-visible exceptions, or SDK-owned public argument objects, not internal interrupt objects.

### Run, memoization, and step semantics

Function execution requests have two distinct boundaries:

- `on_run_start` marks that the SDK is about to invoke the function handler for this request.
- `on_memoization_end` marks that memoized step replay is complete and newly executed user code may run.

This distinction is required for the idempotent logger. Middleware that needs a request-level execution boundary should use `on_run_start` or `wrap_function_handler`. Middleware that needs to suppress replayed user code and enable behavior only after replay should use `on_memoization_end`.

The per-request function lifecycle is:

1. Parse the request, fetch batch data when needed, and load memoized step state.
2. Run `transform_function_input`.
3. Run `on_run_start`.
4. Enter `wrap_function_handler`.
5. If there are no memoized steps, run `on_memoization_end` before the first handler line executes.
6. Invoke the function handler and replay memoized step outputs and memoized step errors as the handler reaches those step calls.
7. If memoized state existed, run `on_memoization_end` exactly once when the SDK reaches the end of available memoized step state.
8. Continue with newly executed user code, step planning, step callback execution, or final function return.
9. Run `on_run_complete` if the wrapped handler path produces a final function output.
10. Run `on_run_error` if the wrapped handler path raises a user-visible `Exception`.

`on_memoization_end` fires on every execution request that reaches handler execution after memo processing, even when there are no memoized steps. With no memoized steps, it fires before the first user handler code can run. With memoized steps, it fires after the final available memo is consumed and before the next non-replayed user code can run. If the final available memo is an error, `on_memoization_end` fires before the memoized `inngest.StepError` is raised back into user code.

Internal response interrupts for step planning, step scheduling, sleeps, waits, and sends are not run completion or run errors. They should not fire `on_run_complete` or `on_run_error`. `wrap_request` can still observe the produced SDK response at the request boundary.

Memoized step replay semantics:

- Memoized step outputs do not fire `on_step_start`, `on_step_complete`, `on_step_error`, or `wrap_step_handler`.
- Memoized step errors do not fire step callback hooks. They are replayed to user code as `inngest.StepError`.
- Middleware that needs to inspect or mutate memoized step data should use `transform_function_input` and the `steps` mapping.
- `on_memoization_end` is the only notification hook that marks the transition from memoized replay to live user code.

Step operation and step callback semantics:

- `wrap_step` wraps the SDK step operation boundary when user code reaches a step method.
- `wrap_step_handler`, `on_step_start`, `on_step_complete`, and `on_step_error` apply only when a `step.run` callback actually executes in the current request.
- Step planning without callback execution does not fire step callback hooks.
- Step sends, sleeps, waits, and invokes are step operations, but they do not have a user callback. They may be observed by `wrap_step`; they do not fire `wrap_step_handler`.
- A successful step callback fires `on_step_start`, then `wrap_step_handler`, then `on_step_complete`.
- A step callback that raises an `Exception` fires `on_step_error` with the original exception raised by user code.

`RetryAfterError` and `NonRetriableError` raised inside a step callback are still original user exceptions for step middleware. `on_step_error` receives the concrete error object raised by the callback. The SDK then converts the error into the appropriate internal step response interrupt as described in [`foundation/retry_control_flow_errors.md`](./retry_control_flow_errors.md).

Parallel and planned step semantics:

- Parallel step discovery can encounter multiple step operations in one handler pass, but it does not execute multiple new step callbacks in that request.
- During parallel discovery, planned steps do not fire step callback hooks.
- During targeted parallel step execution, only the targeted step callback fires `wrap_step_handler`, `on_step_start`, `on_step_complete`, or `on_step_error`.
- Non-targeted parallel steps are skipped for that request and do not fire step callback hooks.
- When `disable_immediate_execution` causes a step to be planned instead of executed, step callback hooks do not fire.

Retry and final-attempt semantics:

- Function-level `on_run_error` fires for each request attempt that raises a user-visible function error, whether or not the executor will retry the function.
- Step-level `on_step_error` fires for each actual step callback attempt that raises, whether or not the executor will retry the step.
- Final-attempt status should be exposed through existing attempt metadata on `ctx` or an explicit future payload field if needed; hook firing does not change just because an attempt is final.
- If user code catches a memoized `inngest.StepError` and returns successfully, the request fires `on_run_complete`, not `on_run_error`.

`on_failure` handlers should run through the same middleware lifecycle as ordinary functions. The failure handler is a separate function execution with its own `function` info, `ctx`, memoization boundary, run hooks, step hooks, and wrappers.

### Send-side behavior

Send middleware applies to both direct client sends and function-scoped sends. Python should match the TypeScript lifecycle concepts with Pythonic snake_case hook names:

- `transform_send_event` modifies send-side events before they are sent.
- `wrap_send_event` wraps the send operation and observes success, failure, retries, and cleanup for that operation.

The middleware stack depends on the active send scope:

- `client.send(...)` outside function execution uses client-level middleware only.
- `client.send(...)` inside function execution uses the active function execution middleware stack.
- `ctx.step.send_event(...)` uses the active function execution middleware stack.

The active function execution middleware stack is the client middleware followed by function middleware. Function-level middleware is effectively appended to the client-level middleware array for that function execution. Therefore function-scoped sends run both client and function middleware exactly once, in that order.

Do not implement this as "skip middleware". Implement it as active send middleware scope selection. Internally, `client.send(...)` should select the correct middleware scope:

```python
scope = _current_send_scope.get(None)

if scope is not None and scope.active and scope.client is self:
    middleware = scope.middleware  # client middleware + function middleware
    function = scope.function
else:
    middleware = MiddlewareManager.from_client(...)
    function = None
```

The lower-level send transport helper must not create its own middleware manager. It should receive the selected middleware scope from `client.send(...)`. This avoids the current double-invocation hazard where `step.send_event(...)` runs function-scoped middleware and then delegates to `client.send(...)`, which would otherwise rebuild and run client middleware again.

Use a `ContextVar` to expose the active send scope during function execution. The scope object should include at least the client, composed middleware stack, request info, function info, and an `active` flag. The function execution path should set the scope before invoking the wrapped function handler and clear it in `finally`:

```python
scope = SendMiddlewareScope(...)
token = _current_send_scope.set(scope)
try:
    ...
finally:
    scope.active = False
    _current_send_scope.reset(token)
```

The `active` flag protects against copied context in background asyncio tasks. A task created during a function may inherit the `ContextVar`, but after function execution exits, `scope.active` is false and later `client.send(...)` calls fall back to client-level middleware. If execution moves to another thread without context propagation, `client.send(...)` also falls back to client-level middleware.

Send event preparation and hook ordering:

1. Normalize the caller input to a list of send-side `Event` objects.
2. Apply serializers needed to normalize event data to object-shaped JSON.
3. Validate that each event has object-shaped JSON event data.
4. Run `transform_send_event` in middleware order.
5. Validate transformed events again before constructing a wire payload.
6. Apply outer wire serializers such as encryption.
7. Run `wrap_send_event` around the actual send operation.

Middleware should see prepared send-side `Event` objects with JSON-object-shaped `data`, not arbitrary raw Pydantic models, encrypted wire envelopes, or caller-owned event instances. This preserves event-mutating middleware assumptions. If middleware mutates event data into a non-object value, the SDK should fail before sending or constructing the step response.

For direct client sends, the actual send operation is the HTTP request and retry loop. `wrap_send_event` should observe retries and final send success or failure because the SDK owns network I/O in that path.

For `ctx.step.send_event(...)`, the send operation is creation of the step send response. The Python SDK does not directly perform executor-side event delivery for that path, so network delivery retries and failures are not observable in Python middleware. `wrap_send_event` can observe step response construction and errors raised while preparing that response.

### Migration plan

This is a v0.6 breaking change. Remove the old middleware hook contract completely in v0.6 and update all in-repo middleware at the same time. Do not keep deprecated shims for the old hook names, `MiddlewareSync`, or `TransformOutputResult`. The `Middleware` symbol is reused for the new lifecycle contract only.

In-repo middleware must be migrated in the same SDK change:

- `LoggerMiddleware`
- `RemoteStateMiddleware`
- `SentryMiddleware`

`LoggerMiddleware` migration:

- Old: `transform_input` replaces `ctx.logger` with `FilteredLogger`.
- Old: `before_execution` enables logging after memoized steps are exhausted.
- New: Preserve `ctx.logger` identity and use the idempotent logger behavior from [`foundation/use_logging_filter.md`](./use_logging_filter.md).
- New: Use `on_memoization_end` as the live-code boundary for replay-aware logging.
- New: Use wrapper cleanup to restore any temporary logging state after success, user errors, and internal response interrupts.

`RemoteStateMiddleware` migration:

- Old: `transform_input` calls `driver.load_steps(steps)` and stores `run_id`.
- Old: `transform_output` stores step output externally and replaces the output with a marker.
- New: Use `transform_function_input` to load and mutate memoized step data before the handler observes it.
- New: Use `wrap_step_handler` for step callback output storage and replacement.
- New: Keep remote-state behavior scoped to `STEP_RUN` outputs; do not apply it to function outputs or non-callback step operations.

`SentryMiddleware` migration:

- Old: `transform_input` sets function, event, and run tags.
- Old: `transform_output` captures errors.
- Old: `before_response` flushes Sentry.
- New: Use `transform_function_input` or `on_run_start` to set tags from `ctx`, request info, and function info.
- New: Use `on_run_error` and `on_step_error` to capture function and step exceptions.
- New: Use `wrap_request` cleanup to flush Sentry at the request boundary.

`pkg/inngest_encryption` is released separately from the main SDK and needs a staged migration:

1. Before releasing SDK v0.6, release `inngest_encryption` 0.1.1 with the only change being a dependency constraint of `inngest<0.6`.
2. After prereleasing SDK v0.6, update `inngest_encryption` to expose `EncryptionSerializer` and release a compatible version with dependency constraint `inngest>=0.6,<0.7`.

`EncryptionMiddleware` is not a v0.6 middleware. Encryption is a wire-stage payload serializer as specified in [`foundation/payload_serializers.md`](./payload_serializers.md). The compatible `inngest_encryption` release should reject or remove the old middleware class unless the package deliberately keeps a migration-only alias that fails with a clear error.

Transform hooks run forward in registration order. Each hook receives the result returned by the previous hook:

- `transform_function_input`
- `transform_send_event`
- `transform_step_input`

Transform hook errors abort the relevant operation because transform hooks produce the value the SDK will use. `transform_function_input` errors abort the function request, `transform_send_event` errors abort the send, and `transform_step_input` errors abort the step planning or execution path.

Wrapper hooks use onion ordering. The first middleware in registration order is the outermost wrapper. Code before `next()` runs in registration order; code after `next()` and `finally` cleanup unwinds in reverse order:

- `wrap_function_handler`
- `wrap_request`
- `wrap_send_event`
- `wrap_step`
- `wrap_step_handler`

Wrapper hook errors propagate according to the wrapped operation. A wrapper that raises before or around `next()` aborts that operation. A wrapper may catch and replace an output or error; the replacement becomes the operation result.

Notification hooks run forward in registration order:

- `on_register`
- `on_memoization_end`
- `on_run_start`
- `on_run_complete`
- `on_run_error`
- `on_step_start`
- `on_step_complete`
- `on_step_error`

Runtime notification hook errors should be logged and should not fail user execution. `on_register` is registration-time setup, so `on_register` errors should fail registration immediately.

Cleanup and finally-style behavior belongs in wrapper hooks, not notification hooks.
