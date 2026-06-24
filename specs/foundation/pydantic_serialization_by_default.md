# Enable Pydantic serialization by default

Area: Serialization
Change type: Quality of life

## Problem

Omitting `serializer` from `Inngest(...)` currently means the SDK does not serialize custom Python objects. Function output, step output, and event data must already be compatible with `json.dumps`, unless the user explicitly passes `serializer=inngest.PydanticSerializer()` or another custom serializer.

This makes common Python data models harder to use than necessary and creates repeated boilerplate around Pydantic models.

## Solution

Omitting `serializer` enables `PydanticSerializer` by default. Users can pass `serializer=None` to preserve strict JSON-only behavior, pass one custom `PayloadSerializer` to replace the default, or pass an ordered serializer sequence to compose custom serializers with Pydantic explicitly.

Default serialization should improve common model ergonomics without applying custom serialization to unknown output types that only use the raw JSON path.

## Related work

### Blocking

This spec depends on [`foundation/payload_serializers.md`](./payload_serializers.md) for the public `PayloadSerializer` protocol, serializer chain ordering, and application-stage versus wire-stage boundaries.

This spec depends on [`foundation/infer_output_types.md`](./infer_output_types.md) for typed round-trip function and step outputs.

This spec depends on [`foundation/remove_our_json_type.md`](./remove_our_json_type.md) for the event-data object-shape contract and removal of the public `JSON` alias.

### Non-blocking

This spec is related to [`foundation/separate_produced_and_consumed_events.md`](./separate_produced_and_consumed_events.md) for send-side versus receive-side event data handling.

## Out of scope

This does not make arbitrary objects valid everywhere. It also does not remove support for custom serializers or strict JSON-only behavior.

## Risks

This is a breaking behavior change because values that previously failed as non-JSON-serializable may now be transformed and accepted. Error timing and error messages may also change from `OutputUnserializableError` to Pydantic serialization or validation errors.

## Implementation

```python
client = inngest.Inngest(app_id="app")
# Uses [PydanticSerializer()] by default.
```

Users can provide a custom serializer without Pydantic:

```python
client = inngest.Inngest(
    app_id="app",
    serializer=MySerializer(),
)
```

Users can combine a custom serializer with Pydantic by passing an explicit ordered sequence:

```python
client = inngest.Inngest(
    app_id="app",
    serializer=[
        inngest.PydanticSerializer(),
        MySerializer(),
    ],
)
```

Users can explicitly disable custom serialization and preserve strict JSON-only behavior:

```python
client = inngest.Inngest(
    app_id="app",
    serializer=None,
)
```

This requires a constructor sentinel internally so the SDK can distinguish omitted `serializer` from explicit `serializer=None`.

Constructor normalization:

- Omitted `serializer` becomes `[PydanticSerializer()]`.
- `serializer=None` becomes `[]`.
- `serializer=MySerializer()` becomes `[MySerializer()]`.
- `serializer=[PydanticSerializer(), MySerializer()]` becomes that exact ordered chain.

### Pydantic version support

`PydanticSerializer` targets Pydantic v2 only. The package dependency is `pydantic>=2.11.0`, and the serializer should use v2 APIs such as `pydantic.TypeAdapter`, `model_dump(mode="json")`, and `model_validate`.

Pydantic v1 compatibility is out of scope for v0.6. The SDK should not import from `pydantic.v1`, branch on Pydantic major version, or support v1-only APIs such as `.dict()` and `parse_obj()` in `PydanticSerializer`.

If a user needs Pydantic v1 model support, they can provide a custom `PayloadSerializer` that converts their objects to and from JSON-compatible values.

### Payload serializer chain semantics

The constructor accepts `PayloadSerializer | Sequence[PayloadSerializer] | None`, using the protocol and `PayloadSerializerContext` from [`foundation/payload_serializers.md`](./payload_serializers.md).

Serialization runs configured serializers in order. Each serializer receives the output of the previous serializer and returns either a transformed value or the original value unchanged. Deserialization runs the same configured chain in reverse for typed round-trip boundaries.

Any serializer exception is treated as a real serialization or deserialization failure and stops the chain.

If serialization leaves the value unchanged, the SDK validates the resulting value through the raw JSON path for that boundary. If deserialization leaves a typed boundary as raw JSON when a Python target type is required, fail with a clear deserialization error. Raw JSON boundaries may keep returning raw JSON values.

`PydanticSerializer` is an application-stage serializer. It runs before wire-stage serializers such as `EncryptionSerializer` when serializing and after wire-stage serializers when deserializing.

Passing a sequence is the only way to keep Pydantic when adding a custom serializer. Passing a single custom serializer replaces the default Pydantic serializer.

Default serialization applies to:

- Send-side event data input in `client.send`, `client.send_sync`, and step send-event helpers
- `step.invoke_by_id(..., data=...)` input serialization
- Function outputs when the return type is explicitly supplied or inferred
- `step.run` outputs when the return type is explicitly supplied or inferred
- `step.invoke(function=..., data=...)` input serialization and validation, using the invoked function's invocation data type
- `step.invoke(function=...)` output deserialization, using the invoked function's output type
- Typed trigger `ReceivedEvent.data`, invocation `FunctionInvoked.data`, and `step.wait_for_event()` data deserialization

Default serialization does not mean every arbitrary object is accepted in every position. The SDK should distinguish one-way JSON boundaries from round-trip boundaries.

### Event data preparation

Event data must be object-shaped at the prepared event and wire boundary, but the raw Python input may be a serializer-supported object.

```python
client.send(inngest.Event(name="user.created", data=User(...)))
```

With the default serializer, this is valid if `User(...)` serializes to a JSON-compatible object. The SDK must reject it if serialization produces a list, scalar, or `null` as the top-level event data value.

Nested serializer-supported values inside an object-shaped payload are also valid:

```python
client.send(
    inngest.Event(
        name="user.created",
        data={
            "user": User(...),
            "created_at": datetime.datetime.now(),
        },
    )
)
```

The send preparation pipeline is:

- Accept raw event data input as `object | None`.
- Normalize omitted or explicit `None` event data to `{}`.
- Serialize raw event data with configured application-stage serializers when custom serialization is enabled.
- Verify that the serialized top-level event data is a JSON-compatible object.
- Run `transform_send_event` middleware with `event.data` normalized to `dict[str, Any]`.
- Apply configured wire-stage serializers.
- Send object-shaped event data or a documented wire envelope.

Custom serializers may support arbitrary Python values as raw event data input, but they must produce a JSON-compatible object for event data. The prepared event observed by middleware and sent to Inngest always has `data: dict[str, Any]`.

### Middleware ordering

Send-side application-stage serialization and object-shape validation happen before `transform_send_event` middleware runs. Middleware should not receive raw Pydantic models or other arbitrary Python objects in `event.data`.

This preserves middleware and encryption assumptions that event data supports mapping operations and can be JSON-encoded after SDK preparation.

One-way JSON boundaries only need to produce JSON. They may use the default serializer without a known target type:

- `client.send(...)`, `client.send_sync(...)`, and step send-event helpers
- `step.invoke_by_id(..., data=...)`, since the target function may live outside the current Python process or SDK
- Untyped send-side event data

### One-way serialization convention

One-way boundaries need a separate serialization convention from round-trip boundaries. The existing internal behavior for unknown round-trip outputs should continue returning the value unchanged when no target type exists, because unknown round-trip outputs must remain raw JSON and must not be transformed by the default serializer.

For one-way boundaries that support custom objects and do not have a more specific target schema, call configured serializers with `PayloadSerializerContext.typ = object`. This gives serializers a stable signal that the SDK needs best-effort JSON serialization without later deserialization into a target type.

After one-way serialization, validate that the result is JSON-compatible before handing it to `httpx`, step options, middleware-normalized event data, or response construction. Event data has the additional constraint that the serialized top-level value must be a JSON object.

If `serializer=None`, one-way serialization returns the original value and still performs the same JSON-compatibility validation. This preserves strict JSON-only behavior.

Round-trip boundaries must deserialize JSON back into a predictable Python type:

- Function output when another function invokes it
- `step.run` output
- `step.invoke(function=...)` output
- Typed trigger `ReceivedEvent.data`
- Typed invocation `FunctionInvoked.data`
- Typed `step.wait_for_event()` results

For round-trip boundaries, custom serialization requires a known type. Unknown output types use raw JSON serialization and deserialization instead of the custom serializer. Raw JSON mode follows normal JSON semantics and may normalize Python-specific shapes, such as tuples replaying as lists. If users need those values to deserialize back into their original Python type, they must provide an inferred or explicit output type.

### Typed deserialization failures

Typed deserialization and validation failures should follow the retry semantics of the boundary where they occur:

- Trigger `ReceivedEvent.data` validation fails before the handler is called and fails the function run as non-retryable. Retrying the same event payload will not make it satisfy the declared schema.
- `FunctionInvoked.data` validation fails before the handler is called and fails the function run as non-retryable.
- `step.wait_for_event()` data validation fails as a non-retryable step-level error. The SDK should return a non-retryable step response for the wait step, and the later memoized step error should replay to user code as `inngest.StepError`.
- Function output, `step.run` output, and `step.invoke(function=...)` output serialization or deserialization failures follow their existing output error paths. They are not trigger-input validation failures.

These rules apply whether the failing serializer is `PydanticSerializer` or a user-provided serializer in the same boundary.

### Round-trip output types

Default Pydantic serialization for round-trip function and step outputs assumes output type inference is available. If an output type is explicit or inferred, the SDK may use the configured serializer for both serialization and deserialization.

Untyped round-trip outputs continue using raw JSON serialization and deserialization. If an untyped round-trip output returns a value that is not raw-JSON-compatible, fail with a clear error telling the user to add a return annotation or pass `output_type`.

Do not use the one-way `typ=object` serialization convention for round-trip outputs.

### `on_failure` output

`on_failure` handler output is a one-way response. It is never deserialized by `step.invoke(function=...)`, so it does not need output type inference and should not require a return annotation.

With default serialization enabled, `on_failure` output should use the one-way serialization convention with `typ=object`. This lets `on_failure` handlers return Pydantic models or other serializer-supported values without annotations, as long as serialization produces a JSON-compatible value.

If `serializer=None`, `on_failure` output must already be raw JSON-compatible. If one-way serialization produces a value that is not JSON-compatible, fail with the same output serialization error path used for other handler outputs.

### Invocation input

`step.invoke(function=..., data=...)` input is one-way. The invoked function receives it as invocation event data, so it must serialize to a JSON object.

If the invoked function has an explicit invocation data type, use that type for serialization and validation. If the invoked function does not have an explicit invocation data type, use the one-way serialization convention with `typ=object`.

In both cases, normalize `None` to `{}` and reject serialized top-level values that are not JSON objects. If `serializer=None`, invocation input must already be raw JSON-object-compatible.

`step.invoke_by_id(..., data=...)` follows the same one-way input rule because the target function may not be available in the current Python process. Its output remains `object`.

### Strict JSON-only opt-out

If `serializer=None` is passed, custom serialization and deserialization are disabled. Typed non-JSON data models therefore require the default serializer or a user-provided serializer.

This applies to every custom-serialization-capable boundary:

- Send-side event data in `client.send`, `client.send_sync`, and step send-event helpers must already be raw JSON-object-compatible.
- Invocation input in `step.invoke(function=..., data=...)` and `step.invoke_by_id(..., data=...)` must already be raw JSON-object-compatible.
- Function output and `step.run` output must already be raw JSON-compatible, even when an output type is explicit or inferred.
- `on_failure` output must already be raw JSON-compatible.
- Typed trigger `ReceivedEvent.data`, typed `FunctionInvoked.data`, and typed `step.wait_for_event()` results cannot rely on custom deserialization.

Errors in this mode should make the opt-out visible: custom serialization is disabled because `serializer=None`; convert the value to raw JSON-compatible data or configure a serializer.

### Tests

Add constructor and serializer-chain tests:

- Omitted `serializer` creates a chain containing `PydanticSerializer`.
- `serializer=None` creates an empty chain and disables custom serialization.
- `serializer=MySerializer()` creates a one-item chain containing only `MySerializer`.
- `serializer=[PydanticSerializer(), MySerializer()]` preserves that order.
- `serializer=[MySerializer(), PydanticSerializer()]` preserves that order.
- A serializer that does not apply returns the original value unchanged and allows the next serializer to run.
- Any serializer exception stops the chain and surfaces as a serialization or deserialization failure.
- If no serializer handles serialization, raw JSON-compatible values still work and non-compatible values fail according to the boundary.
- `PydanticSerializer` uses Pydantic v2 APIs and supports the package's declared minimum Pydantic version.
- Pydantic v1-only APIs are not required for `PydanticSerializer`.

Cover async and sync paths where behavior diverges, including `send`, `send_sync`, async and sync step send-event helpers, async and sync `step.run`, and async and sync invoke helpers where practical.

Add send-side event-data tests:

- `client.send(Event(data=User(...)))` works when `User` serializes to a JSON object.
- `client.send_sync(Event(data=User(...)))` works when `User` serializes to a JSON object.
- Async and sync step send-event helpers work with `Event(data=User(...))`.
- Nested serializer-supported values inside object-shaped event data work, such as `Event(data={"user": User(...), "created_at": datetime.datetime(...)})`.
- Top-level event data that serializes to a list, scalar, or `null` is rejected.
- Top-level list or scalar event data is rejected even if it is otherwise JSON-compatible.
- Omitted or explicit `None` event data still normalizes to `{}`.
- `transform_send_event` sees `event.data` as `dict[str, Any]`, not as the raw model.
- Wire-stage serializers such as `EncryptionSerializer` see normalized event data after send middleware and continue to work.

Add raw JSON versus typed round-trip tests:

- Untyped `step.run` returning a raw JSON-compatible tuple may replay as a list.
- Annotated `step.run` returning `tuple[int, int]` replays as a tuple.
- `step.run(..., output_type=tuple[int, int])` replays as a tuple.
- Untyped function output follows raw JSON serialization and deserialization behavior.
- Annotated or explicit function output uses the serializer for typed round-trip behavior.
- Untyped round-trip output returning a Pydantic model fails even though the default serializer could dump it.
- Untyped round-trip output returning any non-raw-JSON-compatible value fails with an error telling the user to add a return annotation or pass `output_type`.
- `serializer=None` with typed tuple or Pydantic output fails unless the value is already raw JSON-compatible and no typed reconstruction is required.

Add typed receive-side tests after the typed-event work lands:

- Typed trigger `ReceivedEvent.data` deserializes to the declared model by default.
- Typed `FunctionInvoked.data` deserializes to the declared invocation model by default.
- Typed `step.wait_for_event()` data deserializes to the declared event model by default.
- Invalid typed trigger payload fails non-retryably with a clear validation error.
- Invalid invocation payload fails non-retryably with a clear validation error.
- Invalid typed `wait_for_event()` payload returns a non-retryable step-level error and replays to user code as `inngest.StepError`.
- `serializer=None` disables custom deserialization, so typed receive-side models that require Pydantic or custom conversion fail clearly.
