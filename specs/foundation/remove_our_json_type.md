# Remove the public `JSON` type alias

Area: Serialization
Change type: Typing

## Problem

`JSON` is exported from the public API and used for event data typing, but the alias is not a true recursive JSON type. It also suggests that event payloads can be any JSON value, even though Inngest event data must be a JSON object.

## Solution

Remove the public `JSON` type alias entirely and replace public uses with concrete annotations that match each surface. Event data should be typed as `dict[str, Any]` unless a typed event model supplies a narrower object shape. `EventType[...]` is the preferred replacement only for event-data type safety; it is not a replacement for general step or function output annotations.

## Related work

### Non-blocking

[`foundation/separate_produced_and_consumed_events.md`](./separate_produced_and_consumed_events.md) defines the broader split between send-side `Event` and receive-side `ReceivedEvent`. That spec owns the model split; this spec constrains the replacement for the removed `JSON` alias so event data remains object-shaped and received `data: null` is normalized to `{}`.

## Out of scope

This does not attempt to define or export a fully recursive JSON type.

## Risks

Removing a public alias is a breaking change for users who import `inngest.JSON`. The migration is small, but release notes should call out that typed event models are the preferred replacement for event-data type safety.

## Open questions

- Should `transform_send_event` receive raw send-side `Event.data` values, such as Pydantic models, or prepared object-shaped `dict[str, Any]` data after application serializers run? Prepared data gives middleware a stable mapping-shaped contract. Raw data preserves application objects for middleware that wants to inspect model types or methods.

## Implementation

```python
# Before
data: Mapping[str, JSON]

# After
data: dict[str, Any]
```

Delete the central `JSON` alias instead of keeping it as a private implementation detail. If a narrow implementation still needs to describe decoded JSON-like values, use local private annotations near that code.

### Replacement guidance

Use explicit annotations based on the surface being typed:

- Event data should use `dict[str, Any]`.
- Event-data helpers that only need read-only object behavior should use `Mapping[str, Any]`.
- Known object outputs should use `dict[str, Any]`, `Mapping[str, Any]`, or a concrete typed model.
- Intentionally heterogeneous JSON-like arrays should use `list[Any]`; prefer a narrower element type such as `list[dict[str, Any]]` when the array shape is known.
- Unknown step or function outputs that the code does not inspect should use `object`.

Encryption helper annotations should follow the same object-shaped event-data rule. Helpers that process event data should accept `Mapping[str, Any]` and return `dict[str, Any]` or `Mapping[str, Any]` based on their actual return semantics. Lower-level helpers that can decrypt arbitrary JSON-shaped values may use `object` at that local boundary.

### Event data types

Removing `JSON` must not widen event data to arbitrary values. Event data is always a JSON object.

- Prepared send-side event data should be typed as `dict[str, Any]`.
- Omitted or explicit `None` send-side event data should normalize to `{}` before sending.
- Non-object send-side event data is invalid.
- Untyped receive-side `ReceivedEvent.data` should be typed as `dict[str, Any]`.
- Server `data: null` should normalize to `{}` for untyped received events.
- Typed receive-side event data should use the `EventType[...]` data model and should still represent an object-shaped payload.

`Any` remains appropriate for intentionally mixed step or function outputs, but it is not the default replacement for event data.

### Middleware ordering

Send middleware ordering depends on the open question above. If `transform_send_event` receives prepared events, it should see `event.data` as `dict[str, Any]`, not a raw Pydantic model or another arbitrary serializer-supported object.

If typed event creation accepts a model or another structured input, the SDK must eventually convert it to an object-shaped `dict[str, Any]` before sending. Non-object serialized event data is invalid and should be rejected before the event leaves the SDK.

This preserves middleware assumptions that event data supports mapping operations such as `.get(...)`, including the encryption middleware.

### Tests

Add test coverage for public API removal:

- `JSON` is absent from `inngest.__all__`.
- `from inngest import JSON` fails.
- `inngest.JSON` is absent.
- The central `_internal.types.JSON` alias is deleted.

Add type-test coverage for replacement annotations:

- Event data examples use `dict[str, Any]` or typed event models.
- Step and function output examples no longer use `inngest.JSON`.
- Heterogeneous output arrays use `list[Any]` only when the element shape is intentionally mixed.
- Known object arrays use narrower annotations such as `list[dict[str, Any]]`.

Add runtime regression coverage for event data behavior:

- Send-side omitted or explicit `None` event data normalizes to `{}`.
- Non-object send-side event data is rejected.
- Untyped received `data: null` normalizes to `{}`.
- Send middleware sees `event.data` as a mapping-shaped `dict[str, Any]`.
- `EncryptionSerializer` still works with normalized event data.

Run the package and type-check targets that exercise `pkg/inngest`, `pkg/inngest_encryption`, and the main test suite.
