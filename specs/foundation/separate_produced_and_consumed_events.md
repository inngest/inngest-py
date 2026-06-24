# Split send-side `Event` from receive-side `ReceivedEvent`

Area: Events
Change type: Architecture

## Problem

A single `Event` class is currently used for both sending and receiving. Producer-side and consumer-side events have different guarantees: send-side `id` and `ts` are optional, while receive-side `id` and `ts` are guaranteed.

Using one model for both directions leaks sentinel defaults into send serialization and makes it too easy to forward server-populated metadata like `id` and `ts` into a new event.

## Solution

Use independent send and receive models with no inheritance between send-side `Event` and receive-side `ReceivedEvent`. Send APIs accept `Event`; runtime consumer APIs return `ReceivedEvent` or an `EventType[...]` subclass.

Typed event definitions build on this split: `EventType[...]` is a receive-side event type plus reusable event definition, and its `create(...)` method produces a send-side `Event`.

## Related work

### Blocking

[`foundation/remove_our_json_type.md`](./remove_our_json_type.md) defines the event-data object-shape contract that this split uses for send-side prepared events and untyped receive-side events.

### Non-blocking

[`foundation/payload_serializers.md`](./payload_serializers.md) defines payload serialization, including the application-stage serializers that normalize raw send-side event data before middleware and wire-stage serializers such as encryption.

[`foundation/typed_event_input_data.md`](./typed_event_input_data.md) builds on this split with `EventType[...]` and `FunctionInvoked[...]`.

## Out of scope

This does not change the Event API wire format, server-populated event metadata, or backend payload canonicalization behavior.

## Risks

This is a breaking type-model change. Existing code that passes `ctx.event` back into `client.send()` must be updated to construct a new send-side event explicitly.

## Implementation

Keep `Event` as the public send-side model. Add `ReceivedEvent` as the public receive-side model.

Split the existing internal event module in place to minimize churn:

- `pkg/inngest/inngest/_internal/server_lib/event.py` exports both `Event` and `ReceivedEvent`.
- `Event` is producer-side only and is accepted by send helpers.
- `ReceivedEvent` is consumer-side only and is used for inbound execution payloads, `ctx.event`, `ctx.events`, fetched batch events, and `step.wait_for_event()` results.
- `EventType[...]` and `FunctionInvoked[...]` are receive-side subclasses of `ReceivedEvent`; their detailed API is owned by [`foundation/typed_event_input_data.md`](./typed_event_input_data.md).

Public exports in `pkg/inngest/inngest/__init__.py` must include both `Event` and `ReceivedEvent`.

### Parsing surfaces

Switch inbound execution parsing from `Event` to `ReceivedEvent` everywhere the SDK represents an event received from the Executor or backend:

- `ServerRequest.event`
- `ServerRequest.events`
- `_get_batch()` return values
- `_get_batch_sync()` return values
- `Context.event`
- `Context.events`
- `ContextSync.event`
- `ContextSync.events`
- Async `step.wait_for_event()` return values
- Sync `step.wait_for_event()` return values
- Mocked trigger helpers that construct execution contexts
- Test helper payload parsing, especially `pkg/test_core/test_core/helper.py`
- Failure-event helpers that reconstruct the original event from failure event data

Keep public send-side surfaces typed as `Event`:

- `client.send()`
- `client.send_sync()`
- Async `step.send_event()`
- Sync `step.send_event()`
- Mocked send helpers

```python
SendNameT = typing_extensions.TypeVar("SendNameT", bound=str, default=str)
SendDataT = typing_extensions.TypeVar("SendDataT", default=Any)
ReceivedNameT = typing_extensions.TypeVar(
    "ReceivedNameT",
    bound=str,
    default=str,
)
DataT = typing_extensions.TypeVar("DataT", default=dict[str, Any])


class Event(BaseModel, Generic[SendNameT, SendDataT]):
    """
    Producer side: passed to client.send()
    """

    data: SendDataT = pydantic.Field(default_factory=dict)
    id: str | None = None
    name: SendNameT
    ts: int | None = None


class ReceivedEvent(BaseModel, Generic[ReceivedNameT, DataT]):
    """
    Consumer side: ctx.event
    """

    data: DataT
    id: str
    name: ReceivedNameT
    ts: int
```

Add an internal prepared send-event surface for post-serialization send processing:

```python
class PreparedEvent(BaseModel, Generic[SendNameT]):
    """
    Internal send side after SDK preparation and application-stage serialization.
    """

    data: dict[str, Any]
    id: str | None = None
    name: SendNameT
    ts: int
```

Public send helpers accept `Event[Any, Any]`, normalize it to `PreparedEvent`, pass prepared events to send middleware, then apply wire-stage serializers and build the final wire payload. `PreparedEvent` is internal and should not be exported.

`client.send()` and `step.send_event()` accept send-side `Event` only. `ctx.event`, `ctx.events`, and `step.wait_for_event()` return `ReceivedEvent` or an `EventType[...]` subclass.

Send helpers keep the existing single-or-many shape, but the accepted event objects are send-side only:

```python
SendEventInput = Event[Any, Any] | list[Event[Any, Any]]
```

Apply that input shape to:

- `client.send(events: SendEventInput)`
- `client.send_sync(events: SendEventInput)`
- Async `ctx.step.send_event(..., events: SendEventInput)`
- Sync `ctx.step.send_event(..., events: SendEventInput)`

Send helpers must reject receive-side objects unless the user explicitly converts them to a send-side event. Rejected receive-side objects include `ReceivedEvent`, `EventType` instances, and `FunctionInvoked` instances.

Users should convert received events explicitly:

```python
await client.send(inngest.Event(name=ctx.event.name, data=ctx.event.data))
```

For typed event definitions, users should send with `EventType.create(...)`:

```python
await client.send(UserCreated.create(UserCreatedData(user_id="u1")))
```

Send-side wire semantics:

- If `Event.id is None`, omit `id` from the outgoing payload.
- If `Event.id == ""` or contains only whitespace, fail validation. Empty and whitespace-only strings are not valid event IDs, and callers that want the SDK or backend to assign an ID should use `None`.
- If `Event.ts is None`, the SDK should preserve current behavior and fill `ts` with the current Unix timestamp in milliseconds before sending.
- If `Event.ts == 0`, preserve current compatibility behavior and fill `ts` with the current Unix timestamp in milliseconds before sending.
- If `Event.ts` is a positive integer, preserve it.
- If `Event.ts` is negative, fail validation.
- If `Event.ts` is `True` or `False`, fail validation. In Python, `bool` is an `int` subclass, but booleans are not valid timestamps.
- If `Event.ts` is a non-integer value, fail validation.
- If `Event.data` is omitted or explicitly `None`, normalize it to `{}` before sending. The backend canonicalizes null event payloads to `{}`, so preserving explicit send-side `None` would imply a distinction that is not observable by consumers.

Send-side `Event.data` may accept `Any` at the Python API boundary so users can pass Pydantic models or values handled by custom serializers. Before sending, serializers must serialize the value to JSON-compatible data. The final serialized top-level `Event.data` must be a JSON object, equivalent to `dict[str, Any]`.

If serialized event data is a non-object top-level value such as a list, string, number, boolean, or `None`, fail before sending with a clear event-data validation error. Omitted or explicit `None` is the special case normalized to `{}` before final validation.

This preserves Inngest expression behavior like `event.data.foo` and keeps middleware and encryption hooks operating on object-shaped event data.

For untyped received events, `data: null` from the server should still become `{}` for ergonomic dictionary access. For typed received events, inbound `data: null` should also normalize to `{}` before typed validation so event data remains object-shaped. Typed `data: null` should not become `None` unless a later typed-event spec explicitly broadens event data beyond the object-shaped contract.

`ReceivedEvent` without type parameters defaults to `ReceivedEvent[str, dict[str, Any]]`.

### Invocation events

This spec defines the base send/receive split. [`foundation/typed_event_input_data.md`](./typed_event_input_data.md) owns the detailed typed invocation API.

The split must support `FunctionInvoked[...]` as a receive-side subclass of `ReceivedEvent`. `FunctionInvoked[...]` represents the implicit `inngest/function.invoked` system event that can appear in `ctx.event` and `ctx.events` because every function can be invoked.

`FunctionInvoked[...]` is receive-side only. It must not be accepted by send APIs, `TriggerEvent`, or `step.wait_for_event()`.

Inbound parsing should leave room to construct `ReceivedEvent`, `EventType[...]`, or `FunctionInvoked[...]` depending on the function's typed trigger and invocation metadata.

### Middleware contract

Client send middleware and step send middleware receive internal `PreparedEvent` objects: send-side event objects whose data has already been normalized to `dict[str, Any]`, whose `ts` has been filled, and whose application-stage serialization has already run. This preserves the public send-side/receive-side split while making middleware work with the same object-shaped event-data contract as the wire payload.

Function input middleware receives contexts containing receive-side event objects:

- `ctx.event: ReceivedEvent | EventType[...] | FunctionInvoked[...]`
- `ctx.events: list[ReceivedEvent | EventType[...] | FunctionInvoked[...]]`

The base split does not make received events immutable. Middleware that currently mutates `event.data` may continue to mutate receive-side event data unless the middleware rewrite later narrows that contract.

Middleware should operate on application-level event data, not encrypted wire envelopes. Payload decoding, including encryption and custom serialization, is owned by [`foundation/payload_serializers.md`](./payload_serializers.md).

Typed receive-side conversion to `EventType[...]` and `FunctionInvoked[...]` is owned by [`foundation/typed_event_input_data.md`](./typed_event_input_data.md). This spec only requires that those typed objects are receive-side objects and are not accepted by send helpers.

To forward an event, users must explicitly construct a new send-side event:

```python
received = ctx.event
await client.send(inngest.Event(name=received.name, data=received.data))
```

### Tests

Add focused coverage for:

- Send serialization omits `id=None`.
- Send validation rejects `id=""`.
- Send validation rejects whitespace-only `id`.
- Send serialization fills `ts=None`.
- Send serialization fills `ts=0`.
- Send serialization preserves positive integer `ts`.
- Send validation rejects negative `ts`.
- Send validation rejects boolean `ts`.
- Send validation rejects non-integer `ts`.
- Omitted `Event.data` normalizes to `{}`.
- Explicit `Event.data=None` normalizes to `{}`.
- Serialized non-object top-level `Event.data` fails before send.
- Internal `PreparedEvent.data` is always `dict[str, Any]`.
- Send middleware receives `PreparedEvent` objects with normalized object-shaped data.
- `ReceivedEvent` rejects missing `id` through required-field validation.
- `ReceivedEvent` rejects missing `ts` through required-field validation.
- Untyped received `data: null` becomes `{}`.
- Typed received `data: null` normalizes to `{}` before typed validation.
- `ctx.event` returns `ReceivedEvent` or a receive-side subclass.
- `ctx.events` returns `list[ReceivedEvent]` or receive-side subclasses.
- Fetched batch events return `ReceivedEvent`.
- Async and sync `step.wait_for_event()` return `ReceivedEvent` or a receive-side subclass.
- Send helpers reject `ReceivedEvent`.
- Send helpers reject `EventType` instances.
- Send helpers reject `FunctionInvoked` instances.
- Send middleware hooks receive internal `PreparedEvent` objects.
- Function input middleware receives receive-side event objects.
- Payload serializers, including encryption, continue to see object-shaped event data.
- Pyright or mypy tests cover `Event.id` as `str | None`.
- Pyright or mypy tests cover `ReceivedEvent.id` as `str`.
