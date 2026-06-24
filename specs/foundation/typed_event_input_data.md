# Typed event input data

Area: Events
Change type: Typing

## Problem

`Event.data` and `ctx.event.data` are JSON-shaped mappings. Users who want Pydantic or other typed event data must manually serialize on send and manually deserialize inside every triggered function.

This makes typed event handling repetitive and weakens confidence at function boundaries. It also leaves Python users without a close equivalent to the TypeScript SDK's typed trigger experience.

```python
class UserCreatedData(pydantic.BaseModel):
    user_id: str


await client.send(
    inngest.Event(
        name="user.created",
        data=UserCreatedData(user_id="u1").model_dump(mode="json"),
    )
)


@client.create_function(
    fn_id="handle-user",
    trigger=inngest.TriggerEvent(event="user.created"),
)
async def handle_user(ctx: inngest.Context) -> None:
    data = UserCreatedData.model_validate(ctx.event.data)
    reveal_type(data)  # UserCreatedData
```

## Solution

Add a class-based `EventType[...]` API for typed, reusable event definitions. `EventType` is a receive-side event type and reusable runtime event definition; it is not a send-side event instance. Its `create(...)` method produces the send-side `Event`.

Typed event classes give users one reusable object for triggering, sending, receiving, validating, and narrowing event data. Python cannot match TypeScript's decorator-driven inference, so users who want static checking still annotate `ctx`.

## Related work

### Blocking

[`foundation/separate_produced_and_consumed_events.md`](./separate_produced_and_consumed_events.md) must land first. `EventType[...]` and `FunctionInvoked[...]` are receive-side subclasses of `ReceivedEvent`, while `EventType.create(...)` returns the send-side `Event`.

[`foundation/remove_our_json_type.md`](./remove_our_json_type.md) must land before or with this spec. Send-side `Event.data` needs to accept broad Python input and validate that the serialized top-level event data is a JSON object.

[`foundation/payload_serializers.md`](./payload_serializers.md) and [`foundation/pydantic_serialization_by_default.md`](./pydantic_serialization_by_default.md) must land before or with this spec. Typed event sending and receiving rely on the same serializer behavior for serialization and deserialization.

Do not implement this spec first while the SDK still has a single `server_lib.Event` model with `data: Mapping[str, JSON]`, `id=""`, and `ts=0`. That model conflicts with both typed sending and typed receiving.

### Non-blocking

[`foundation/rewrite_middleware.md`](./rewrite_middleware.md) defines the long-term middleware lifecycle and `transform_function_input` ordering that typed receive-side validation should integrate with.

## Out of scope

This does not make Python infer handler parameter types from decorator arguments. It also does not type arbitrary string triggers, wildcard event patterns, or `step.invoke_by_id(...)` targets that may live outside the current Python process.

## Risks

This is a substantial type-system change. Runtime annotation validation must be clear and predictable, and error messages need to help users distinguish between trigger mismatch, unresolved annotations, and data validation failures. The implicit `FunctionInvoked[...]` branch also adds complexity that users must handle when they rely on exhaustive event narrowing.

## Implementation

Python cannot infer handler parameter types from decorator arguments the way TypeScript can infer from `eventType()`. Users must still annotate `ctx` with `Context[...]` or `ContextSync[...]` when they want static type checking.

Event names are specified as a `Literal[...]` generic argument so the same class can be used both at runtime and in static type annotations. Unlike `ReceivedEvent`, `EventType` does not default the name type to `str`; the first generic argument must provide a concrete event name. The second generic argument is the received data type and defaults to `dict[str, Any]`.

`EventType` data is constrained by the event-data object contract. `DataT` may be a Pydantic model, dataclass, `TypedDict`, plain mapping, or other serializer-supported Python type, but its serialized top-level event data must be a JSON object. `EventType` is not a way to define top-level scalar, list, or `null` event payloads.

The Python type system cannot prove that an arbitrary `DataT` serializes to an object-shaped value, so the SDK must enforce this at runtime. Sending an `EventType` whose data serializes to a top-level scalar, list, or `null` fails before send. Receiving an event whose decoded data is not object-shaped fails before typed validation, except that inbound `data: null` is normalized to `{}` as defined by [`foundation/separate_produced_and_consumed_events.md`](./separate_produced_and_consumed_events.md).

```python
EventNameT = typing_extensions.TypeVar("EventNameT", bound=str)
DataT = typing_extensions.TypeVar(
    "DataT",
    default=dict[str, Any],
)
InvokeDataT = typing_extensions.TypeVar(
    "InvokeDataT",
    default=dict[str, Any],
)
TriggerEventT = typing_extensions.TypeVar(
    "TriggerEventT",
    bound=ReceivedEvent[Any, Any],
    default=ReceivedEvent[str, dict[str, Any]],
)


class EventType(
    ReceivedEvent[EventNameT, DataT],
    Generic[EventNameT, DataT],
):
    ...


class FunctionInvoked(
    ReceivedEvent[Literal["inngest/function.invoked"], InvokeDataT],
    Generic[InvokeDataT],
):
    ...


class Context(Generic[TriggerEventT, InvokeDataT]):
    event: TriggerEventT | FunctionInvoked[InvokeDataT]
    events: list[TriggerEventT | FunctionInvoked[InvokeDataT]]
```

```python
from typing import Literal


class UserCreatedData(pydantic.BaseModel):
    user_id: str


class UserCreated(
    inngest.EventType[Literal["user.created"], UserCreatedData],
):
    pass


await client.send(
    UserCreated.create(UserCreatedData(user_id="u1"))
)


@client.create_function(
    fn_id="handle-user",
    trigger=inngest.TriggerEvent(UserCreated),
)
async def handle_user(
    ctx: inngest.Context[UserCreated, UserCreatedData],
) -> None:
    reveal_type(ctx.event.name)
    # Literal["user.created"] | Literal["inngest/function.invoked"]
    reveal_type(ctx.events)
    # list[UserCreated | FunctionInvoked[UserCreatedData]]

    if isinstance(ctx.event, inngest.FunctionInvoked):
        reveal_type(ctx.event.data)  # UserCreatedData
        return

    reveal_type(ctx.event.name)  # Literal["user.created"]
    reveal_type(ctx.event.id)  # str
    reveal_type(ctx.event.data)  # UserCreatedData
    ctx.event.data.user_id
```

The producer and consumer schemas are intentionally decoupled. Sending an event always produces plain JSON. A Python app can send a Pydantic model, a TypeScript app can send a plain object with the same JSON shape, and the Python consumer deserializes into its declared event data type.

`EventType.create(...)` is a typed convenience for constructing send-side `Event` objects with the correct `name`. Send-side `id` and `ts` remain optional on the returned `Event`; receive-side `id` and `ts` are guaranteed on `ctx.event` and `step.wait_for_event()` results.

```python
send_event = UserCreated.create(
    UserCreatedData(user_id="u1"),
    id=None,
)

reveal_type(send_event.name)  # Literal["user.created"]
reveal_type(send_event.id)  # str | None
```

### `EventType.create(...)`

`EventType.create(...)` constructs a send-side `Event` with the event name extracted from the `EventType` subclass.

```python
@classmethod
def create(
    cls,
    data: DataT | dict[str, Any] | None = None,
    *,
    id: str | None = None,
    ts: int | None = None,
) -> Event[EventNameT, DataT | dict[str, Any]]:
    ...
```

`create(...)` does not eagerly validate or deserialize `data`. It preserves the provided Python value on the returned send-side `Event`; serialization and final event-data validation happen when the event is sent.

For Pydantic-backed event types, passing the declared model is the recommended typed path:

```python
UserCreated.create(UserCreatedData(user_id="u1"))
```

Passing plain JSON with the same shape is accepted at runtime:

```python
UserCreated.create({"user_id": "u1"})
```

Static type checkers may flag the plain-dict form depending on overload support and the declared `DataT`. The runtime should not reject it at `create(...)` time.

If the Pydantic serializer is disabled, passing a Pydantic model fails at send time unless another configured serializer can serialize it. Passing a plain dict works as ordinary JSON.

The final serialized top-level event data must still be a JSON object, as defined in [`foundation/separate_produced_and_consumed_events.md`](./separate_produced_and_consumed_events.md).

Raw `Event(...)` remains supported for untyped sends:

```python
await client.send(
    inngest.Event(name="user.created", data={"user_id": "u1"})
)
```

Every function can also be invoked, so the static type of `ctx.event` always includes the implicit `inngest/function.invoked` system event in addition to the declared trigger events. If no invoke data type is explicitly supplied, the static invocation branch uses `dict[str, Any]`.

`ctx.events` is always present. For non-batch event-triggered or invoked runs, it contains the single event supplied for the run. For batched functions, it contains the batch. Its static type mirrors `ctx.event` as `list[TriggerEventT | FunctionInvoked[InvokeDataT]]`, because invoked runs are represented by the implicit invocation event.

Users can type the invocation branch with the second `Context[...]` argument. This declares the expected invocation input shape for validation and static typing; it does not enable invocation, since all functions are already invocable.

Runtime invocation validation has a convenience default. If a function has exactly one typed event trigger and the handler does not explicitly supply an invocation data type, invoked run data should be validated against that trigger event's data type. This matches the TypeScript SDK's default behavior. This default is runtime-only; Python type checkers still see `FunctionInvoked[dict[str, Any]]` unless the handler supplies the second `Context[...]` argument.

If a function has no typed event trigger, or has multiple typed event triggers and no explicit invocation data type, runtime invocation data remains untyped as `dict[str, Any]`. Users who want invocation validation for multi-trigger functions should provide the second `Context[...]` argument.

The example above uses the same data model for event-triggered and invoked runs. When invocation is more command-like than event-like, users can declare a separate invocation data type:

```python
class ProcessUserInput(pydantic.BaseModel):
    user_id: str
    force: bool = False


@client.create_function(
    fn_id="process-user",
    trigger=inngest.TriggerEvent(UserCreated),
)
async def process_user(
    ctx: inngest.Context[UserCreated, ProcessUserInput],
) -> None:
    if isinstance(ctx.event, inngest.FunctionInvoked):
        reveal_type(ctx.event.data)  # ProcessUserInput
        return

    reveal_type(ctx.event.data)  # UserCreatedData
```

The SDK should infer the function's invocation input type from the second `Context[...]` argument. `step.invoke(function=..., data=...)` should use that type for static typing, serialization, and validation of the invocation payload. `step.invoke_by_id(...)` remains intentionally untyped for invocation input and output because it may target functions outside the current SDK process, outside the current app, or outside Python entirely.

The single typed-trigger invocation default is runtime-only for the invoked function. It does not change the target `Function[..., InvokeDataT]` static type and it does not give callers typed `step.invoke(function=..., data=...)` validation. Callers that want static checking and caller-side serialization/validation for `step.invoke(function=..., data=...)` must ensure the target function declares the second `Context[...]` argument explicitly.

To make typed `step.invoke(function=..., data=...)` possible, the public `Function` type must carry invocation input metadata in addition to output metadata:

```python
OutputT = typing_extensions.TypeVar("OutputT", default=Any)


class Function(Generic[OutputT, InvokeDataT]):
    ...
```

`create_function(...)` should infer the returned function type from the handler:

- Handler output annotation determines `OutputT`.
- A handler annotated as `Context[TriggerEventT, InvokeDataT]` or `ContextSync[TriggerEventT, InvokeDataT]` determines `InvokeDataT`.
- A handler annotated as `Context[TriggerEventT]` or `ContextSync[TriggerEventT]` statically defaults `InvokeDataT` to `dict[str, Any]`.
- An unannotated handler statically defaults `InvokeDataT` to `dict[str, Any]`.

The runtime convenience default that validates invoked data against a single typed trigger does not change the static `Function[..., InvokeDataT]` type. Users who want static checking for `step.invoke(function=..., data=...)` should provide the second `Context[...]` argument on the invoked function.

It also does not change caller-side runtime validation for `step.invoke(function=..., data=...)`: without an explicit `InvokeDataT`, the caller serializes invocation input using the untyped one-way event-data path. The invoked function validates the payload on receipt using the single typed-trigger default.

`step.invoke(function=fn, data=...)` should type `data` from the target function's `InvokeDataT`. `step.invoke_by_id(...)` remains untyped for invocation input and output.

`FunctionInvoked[...]` is receive-side only. The `FunctionInvoked` class is not a user event definition: it should not be accepted by `TriggerEvent`, `step.wait_for_event()`, or send helpers, and it should not expose `create(...)`. Lower-level APIs that accept arbitrary string event names keep their existing string behavior.

### `TriggerEvent` API

`TriggerEvent` should accept both existing string forms and new typed event forms:

```python
inngest.TriggerEvent("user.created")
inngest.TriggerEvent(event="user.created")
inngest.TriggerEvent(UserCreated)
inngest.TriggerEvent(event=UserCreated)
```

The recommended typed form is `TriggerEvent(UserCreated)`.

When `TriggerEvent` receives an `EventType` subclass, the SDK extracts the event name from that subclass and serializes the trigger to the sync payload as the same string event name used today. This spec does not send typed metadata to the server for trigger registration.

Invalid cases should fail with clear errors:

- `TriggerEvent(FunctionInvoked)` fails because invocation is implicit and is not user trigger configuration.
- `TriggerEvent(SomeClass)` fails unless `SomeClass` is an `EventType` subclass.
- `TriggerEvent(UserCreated())` fails because receive-side event instances are not trigger definitions.
- Invalid `EventType` definitions such as `EventType[str]` fail because they do not provide a concrete string `Literal[...]` event name.

Users who want a reusable event definition without a custom data model can omit the second generic argument. The event name remains statically precise, while `data` defaults to `dict[str, Any]`:

```python
class AuditLogged(inngest.EventType[Literal["audit.logged"]]):
    pass


await client.send(AuditLogged.create({"actor_id": "u1"}))
```

`step.wait_for_event()` accepts either an untyped event name or an `EventType` subclass. Passing an `EventType` validates/deserializes the received event data and returns the matching event instance or `None`:

```python
class ApprovalReceived(
    inngest.EventType[
        Literal["app/approval.received"],
        ApprovalReceivedData,
    ],
):
    pass

approval = await ctx.step.wait_for_event(
    "wait-for-approval",
    event=ApprovalReceived,
    timeout=datetime.timedelta(days=7),
)

if approval is not None:
    reveal_type(approval)  # ApprovalReceived
    reveal_type(approval.id)  # str
    reveal_type(approval.data)  # ApprovalReceivedData
```

If a typed `step.wait_for_event(..., event=SomeEventType)` receives an event whose data fails typed validation, `step.wait_for_event()` raises `NonRetriableError`. The SDK should convert that error into a non-retryable step-level response as described in [`foundation/retry_control_flow_errors.md`](./retry_control_flow_errors.md). Retrying the same memoized invalid wait result will not make it satisfy the declared schema.

If the wait times out and returns `None`, no typed validation happens. If `event` is a raw string, no typed validation happens and the return type is `ReceivedEvent[str, dict[str, Any]] | None`.

Multiple triggers are represented in Python annotations as a union of `EventType` subclasses:

```python
class OrgCreatedData(pydantic.BaseModel):
    org_id: str


class OrgCreated(
    inngest.EventType[Literal["org.created"], OrgCreatedData],
):
    pass


@client.create_function(
    fn_id="handle-entity",
    trigger=[
        inngest.TriggerEvent(UserCreated),
        inngest.TriggerEvent(OrgCreated),
    ],
)
async def handle_entity(
    ctx: inngest.Context[UserCreated | OrgCreated],
) -> None:
    reveal_type(ctx.event.data)
    # UserCreatedData | OrgCreatedData | dict[str, Any]

    if isinstance(ctx.event, inngest.FunctionInvoked):
        reveal_type(ctx.event)  # FunctionInvoked[dict[str, Any]]
        reveal_type(ctx.event.data)  # dict[str, Any]
    elif isinstance(ctx.event, UserCreated):
        reveal_type(ctx.event)  # UserCreated
        reveal_type(ctx.event.data)  # UserCreatedData
        ctx.event.data.user_id
    else:
        reveal_type(ctx.event)  # OrgCreated
        reveal_type(ctx.event.data)  # OrgCreatedData
        ctx.event.data.org_id
```

The recommended narrowing pattern is `isinstance(ctx.event, UserCreated)`, since it works with ordinary Python class narrowing. Type checkers that support narrowing by `Literal` fields may also narrow `ctx.event.data` by checking `ctx.event.name`, but the SDK should not rely on all type checkers supporting that pattern.

### Receive-side ordering

Inbound wire payloads are decoded by payload serializers before user middleware sees them. Middleware should see application-level event data, not encrypted wire envelopes.

`transform_function_input` receives `ReceivedEvent` objects with decoded JSON-object `data` in `ctx.event` and `ctx.events`. Middleware may mutate `ctx.event.data` and `ctx.events[*].data` in that hook.

Typed conversion and deserialization into `EventType[...]` and `FunctionInvoked[...]` happen after `transform_function_input` and before the handler is called. This lets encryption and custom serializers run first, preserves middleware that edits event data, and validates the final application-level event data that the handler will receive.

If typed trigger or invocation validation fails after input middleware, the handler is not called and the failure is non-retryable.

For typed receive-side conversion, the SDK must first ensure event data is object-shaped. Untyped and typed inbound `data: null` normalize to `{}` before typed validation. Inbound scalar or list event data fails before typed validation, because event data is object-shaped even when the application-level type is a model.

### Invoked runs

Add a source-of-truth constant for the invocation system event:

```python
class InternalEvents(enum.Enum):
    FUNCTION_INVOKED = "inngest/function.invoked"
```

The SDK detects invoked runs by receiving an event whose name is `inngest/function.invoked`. The Executor is expected to send that event name for function invocation requests.

For invoked runs, convert the received invocation event to `FunctionInvoked[InvokeDataT]` after input middleware and before the handler is called. `ctx.event` is that `FunctionInvoked[...]` instance. For non-batch invoked runs, `ctx.events` contains that same invocation event.

For ordinary event-triggered and batched event-triggered runs, do not synthesize a `FunctionInvoked[...]` runtime event. `ctx.event` and `ctx.events` contain the actual received trigger events. The invocation branch is implicit in static types because every function can be invoked, but it appears at runtime only for invoked requests.

### Batched runs

For batched event-triggered runs, `ctx.events` is the source of truth for the batch. The SDK should convert every batch element independently:

- If a batch event name matches a configured typed trigger, convert that element to the matching `EventType` subclass after input middleware.
- If a batch event name corresponds to a raw string trigger, leave that element as `ReceivedEvent[str, dict[str, Any]]`.
- If a batch mixes multiple typed triggers, each element is converted to its own matching typed event class.

`ctx.event` is the primary event supplied by the Executor in `ServerRequest.event`. The SDK should convert that primary event using the same name-based rules, but it should not choose or synthesize `ctx.event` from `ctx.events[0]`. This preserves Executor-provided primary-event semantics while still giving `ctx.events` precise per-element runtime classes.

### Handler annotation validation

If the handler's `ctx` parameter is unannotated, the SDK should not infer typed event data. Runtime behavior remains untyped:

```python
ctx.event: ReceivedEvent[str, dict[str, Any]] | FunctionInvoked[dict[str, Any]]
ctx.events: list[
    ReceivedEvent[str, dict[str, Any]] | FunctionInvoked[dict[str, Any]]
]
```

If the handler annotates `ctx` as `Context[...]` or `ContextSync[...]`, the SDK should resolve that annotation during function registration or sync. If the annotation cannot be resolved at runtime, registration or sync should fail with a clear error telling the user to use resolvable runtime types or remove the annotation.

Typed trigger declarations must agree with the first `Context[...]` argument:

- `TriggerEvent(UserCreated)` requires `Context[UserCreated, ...]` or a union that includes `UserCreated`.
- Multiple typed triggers require a union covering all typed trigger classes, such as `Context[UserCreated | OrgCreated, ...]`.
- Extra typed event classes in the `Context[...]` trigger union should fail registration or sync, since they do not correspond to configured triggers.

Raw string triggers have no precise event class to validate. If a function mixes raw string triggers and typed triggers, validate only the typed trigger classes. Users who want to model the raw-string branch statically can include `ReceivedEvent[str, dict[str, Any]]` in the first `Context[...]` argument.

The second `Context[...]` argument is the invocation input type. It is not validated against triggers because invocation is implicit for every function.

Resolve annotations with `typing.get_type_hints(..., include_extras=True)` so postponed annotations, forward references, `Annotated`, and type aliases can be handled consistently.

Supported annotation forms:

- `Context[UserCreated]`
- `ContextSync[UserCreated]`
- `Context[UserCreated, InvokeData]`
- `ContextSync[UserCreated, InvokeData]`
- `Context[UserCreated | OrgCreated]`
- `Context[typing.Union[UserCreated, OrgCreated]]`
- `Context[typing.Annotated[UserCreated, ...]]`, after unwrapping `Annotated`
- Type aliases that resolve to supported trigger event types
- Raw `ReceivedEvent[str, dict[str, Any]]` branches for raw string triggers
- Unparameterized `Context` or `ContextSync`, treated as untyped

Unsupported annotation forms should fail with clear errors:

- Unresolvable annotations or forward references fail registration or sync.
- Typed trigger classes configured on the function but missing from the first `Context[...]` argument fail registration or sync.
- Extra typed event classes in the first `Context[...]` argument fail registration or sync.
- Invalid `EventType` definitions such as `EventType[str]` fail because they do not provide a concrete string `Literal[...]` event name.

The SDK should try to resolve annotations when the function is registered. If a forward reference or import cycle cannot be resolved at decorator time, store a pending annotation-validation task on the `Function` registration object and defer validation until sync. Do not silently discard the decorator-time failure.

The pending validation task should store:

- The function ID.
- The handler parameter name.
- The original unresolved annotation or resolution exception.
- A callable that retries annotation resolution and validation.

Sync must run pending annotation validation before serializing the function config. If validation still fails, sync fails with a clear error that names the function ID, handler parameter, and unresolved annotation.

Do not defer annotation validation until a production execution request can call the handler. Unsynced local execution paths, including mocked trigger helpers and tests that invoke a registered function without sync, must run pending annotation validation before constructing the context or calling the handler. If validation still fails, local execution fails before user code runs.

Async and sync handlers follow the same annotation-resolution and validation rules.

Runtime rules:

- `EventType[EventNameT, DataT]` subclasses `ReceivedEvent[EventNameT, DataT]`.
- `EventNameT` must be a single string `Literal[...]`. The SDK extracts that literal value when the subclass is defined and uses it as the event name. `EventType[str]` is invalid because `str` does not provide a concrete runtime event name.
- `DataT` defaults to `dict[str, Any]` when omitted.
- `FunctionInvoked[InvokeDataT]` subclasses `ReceivedEvent[Literal["inngest/function.invoked"], InvokeDataT]` and represents the implicit invocation system event.
- `FunctionInvoked` is receive-side only. The class must not be accepted by send APIs, `TriggerEvent`, or `step.wait_for_event()`.
- Event data is object-shaped. `EventType` data may be represented by any serializer-supported Python type, but its serialized top-level value must be a JSON object. Top-level scalar, list, and `null` event data are invalid for typed events.
- `Context[TriggerEventT]` exposes `ctx.event` as `TriggerEventT | FunctionInvoked[dict[str, Any]]`.
- `Context[TriggerEventT, InvokeDataT]` exposes `ctx.event` as `TriggerEventT | FunctionInvoked[InvokeDataT]`.
- `Context[TriggerEventT]` exposes `ctx.events` as `list[TriggerEventT | FunctionInvoked[dict[str, Any]]]`.
- `Context[TriggerEventT, InvokeDataT]` exposes `ctx.events` as `list[TriggerEventT | FunctionInvoked[InvokeDataT]]`.
- `ctx.events` is always present. Non-batch runs contain one event; batch runs contain the batch events supplied by the Executor.
- All functions remain invocable regardless of whether the handler explicitly supplies `InvokeDataT`. Supplying `InvokeDataT` provides validation and static typing for the invocation payload.
- If `InvokeDataT` is not explicitly supplied and exactly one typed event trigger is configured, runtime invocation validation uses that trigger event's data type. Static typing still defaults the invocation branch to `dict[str, Any]`.
- If `InvokeDataT` is not explicitly supplied and there is no single typed event trigger, invocation data remains untyped as `dict[str, Any]`.
- `step.invoke(function=..., data=...)` uses the invoked function's `InvokeDataT` for static typing, serialization, and validation of `data`.
- `step.invoke_by_id(...)` remains intentionally untyped for invocation input and output. It cannot reliably infer `InvokeDataT` or output type from a string ID.
- `TriggerEvent` accepts either a string event name, `TriggerEvent(event="...")`, or an `EventType` subclass, `TriggerEvent(UserCreated)`.
- If `ctx` is annotated as `Context[...]` or `ContextSync[...]`, resolve and validate the annotation during function registration or sync.
- Typed trigger classes in the first `Context[...]` argument must match the configured typed triggers, ignoring raw string triggers and optional raw `ReceivedEvent[...]` branches.
- If `ctx` is unannotated, use the untyped received-event behavior.
- `step.wait_for_event(..., event=...)` accepts either a string event name or an `EventType` subclass.
- `EventType.create(data, *, id=None, ts=None)` returns a send-side `Event[EventNameT, DataT]` with the class's event name.
- If an `EventType` omits `DataT`, received data remains plain JSON and uses the default `dict[str, Any]` behavior.
- If an `EventType` declares `DataT`, received data is deserialized/validated through the configured serializers after input middleware and before the handler is called, or before `wait_for_event()` returns.
- Before typed deserialization, inbound `data: null` normalizes to `{}` and inbound scalar or list event data fails.
- If the handler explicitly supplies `InvokeDataT`, invocation event data is deserialized/validated through the configured serializers after input middleware and before the handler is called.
- If the handler does not explicitly supply `InvokeDataT`, the single typed-trigger invocation default applies only when the invoked function receives the invocation event. It does not provide static typing or caller-side validation for `step.invoke(function=..., data=...)`.
- If a typed trigger or invocation event fails validation, the function run should fail before the handler is called with a clear validation error. That failure should be non-retryable because retrying the same event payload will not make it satisfy the declared schema.
- If a typed `step.wait_for_event()` result fails validation, the step should fail with a non-retryable step-level response.
- Wildcard event patterns, if supported, should use raw string triggers/waits rather than `EventType`, since matched events may have different payload shapes.

### Public API changes

- Export `Event`.
- Export `ReceivedEvent`.
- Add `EventType[EventNameT, DataT]`.
- Add `FunctionInvoked[InvokeDataT]`.
- `Event.data` accepts `Any` and is serialized before sending. Users do not need to call `model_dump(mode="json")` before passing Pydantic models as event data.
- `ReceivedEvent` is generic over event name and data type.
- `Context` and `ContextSync` are generic over the declared trigger event type and optional invocation data type.
- `TriggerEvent` accepts either a string event name or an `EventType` subclass. The existing keyword form remains `TriggerEvent(event="user.created")` for untyped triggers.
- `ctx.event` always includes the implicit `FunctionInvoked[...]` branch, because every function can be invoked.
- `ctx.events` is always present and uses the same received-event union as `ctx.event`.
- `step.wait_for_event()` returns the explicitly waited event type and does not automatically include `FunctionInvoked[...]`.
- Untyped event names continue to produce `ReceivedEvent[str, dict[str, Any]]`.

This feature reuses the same serializer protocol as output serialization.

### Tests

Add static type coverage with pyright or mypy for:

- `EventType` event-name typing.
- `EventType` data typing.
- `EventType.create(...)` return type.
- `Context[...]` event typing.
- `ContextSync[...]` event typing.
- The `FunctionInvoked[...]` branch.
- Multi-trigger narrowing with `isinstance(ctx.event, UserCreated)`.
- Typed `step.invoke(function=..., data=...)`.
- Untyped `step.invoke_by_id(...)`.
- Typed `step.wait_for_event(...)`.
- Raw string trigger branches modeled with `ReceivedEvent[str, dict[str, Any]]`.

Add runtime coverage for FastAPI and Flask:

- Valid typed trigger data.
- Typed event data whose serialized top-level value is a scalar, list, or `null` fails before send or before typed receive validation, depending on the boundary.
- Typed inbound `data: null` normalizes to `{}` before typed validation.
- Invalid typed trigger data fails before the handler and is non-retryable.
- Valid explicit invocation data type.
- Invalid explicit invocation data type fails before the handler and is non-retryable.
- Runtime invocation validation defaults to the single typed trigger schema when no explicit invoke type is supplied.
- The single typed-trigger invocation default does not provide static typing or caller-side validation for `step.invoke(function=..., data=...)`.
- Multi-trigger invocation remains untyped unless an explicit invoke type is supplied.
- Valid typed `step.wait_for_event()` result.
- Invalid typed `step.wait_for_event()` result fails with a non-retryable step-level response.
- Raw string and typed trigger mixes.
- Batch `ctx.events` with typed event classes.
- Batched mixed typed triggers convert each `ctx.events` element to its matching `EventType` subclass.
- Batched runs preserve the Executor-provided primary event for `ctx.event` instead of selecting `ctx.events[0]`.
- Pydantic serializer disabled.
- Custom serializer round trips.
- Middleware and encryption ordering with typed receive-side validation.
- Clear registration or sync errors for mismatched, missing, extra, or unresolved annotations.
- Deferred annotation validation failures are stored on the `Function` registration object and surface during sync or before unsynced local execution calls the handler.
- Invalid `TriggerEvent` inputs, including `FunctionInvoked`, non-`EventType` classes, receive-side instances, and invalid `EventType[str]` definitions.
