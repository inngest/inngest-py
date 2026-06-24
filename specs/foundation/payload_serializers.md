# Add payload serializer pipeline

Area: Serialization
Change type: Architecture

## Problem

The SDK needs one coherent way to transform payload data as it crosses the application/server boundary. Custom serialization and encryption are both reversible payload transforms, but treating them as ordinary middleware creates ordering problems.

For outbound data, custom serialization must run before encryption so the encrypted value contains the serialized JSON-safe form. For inbound data, encryption must decrypt before custom deserialization can restore application types. A single user-ordered middleware list cannot make both directions correct for every lifecycle hook.

For outgoing step output, the `wrap_step_handler` path needs serialization inside encryption:

```text
step callback returns datetime
-> custom serializer converts datetime to JSON marker
-> encryption encrypts the serialized marker
-> encrypted envelope is sent to Inngest
```

As ordinary wrapper middleware, that requires encryption to be outside the serializer so the after-`next()` path runs serializer first and encryption second.

For memoized step output, the `wrap_step` path needs the opposite after-`next()` order:

```text
Inngest returns encrypted memoized step output
-> encryption decrypts to the serialized marker
-> custom serializer deserializes the marker to datetime
-> user code receives datetime from step.run(...)
```

As ordinary wrapper middleware, that requires the serializer to be outside encryption so the after-`next()` path runs encryption first and serializer second. The same registration order cannot satisfy both `wrap_step_handler` and `wrap_step`.

This also creates a DX problem. Users should not need to reason about middleware onion order, transform order, or whether encryption must be registered before or after a custom serializer. They should be able to declare the payload transformations they need and rely on the SDK to run them in the correct direction.

## Solution

Use a first-class payload serializer pipeline for custom serialization, Pydantic support, encryption, compression, redaction, large-payload externalization, and schema migration.

Keep the public constructor option named `serializer=` for Python ecosystem familiarity. It accepts a single serializer, an ordered serializer sequence, `None`, or omission:

```python
client = inngest.Inngest(
    app_id="app",
    serializer=[
        inngest.PydanticSerializer(),
        MyCustomSerializer(),
        inngest_encryption.EncryptionSerializer(key=...),
    ],
)
```

Payload serializers are listed from application boundary to wire boundary. Serialization runs in list order. Deserialization runs in reverse list order:

```text
Serialize: App value -> PydanticSerializer -> MyCustomSerializer -> EncryptionSerializer -> Inngest
Deserialize: Inngest -> EncryptionSerializer -> MyCustomSerializer -> PydanticSerializer -> app value
```

This makes encryption the outer wire boundary without making users manually invert ordering for inbound paths.

Omitting `serializer` enables the default serializer chain:

```python
client = inngest.Inngest(app_id="app")
# Equivalent to serializer=[inngest.PydanticSerializer()]
```

Passing `serializer=None` disables custom payload transformation and preserves strict JSON-only behavior:

```python
client = inngest.Inngest(app_id="app", serializer=None)
```

Serializers are not ordinary middleware and should not subclass `Middleware`. Middleware is for execution lifecycle behavior. Serializers are for payload boundary transformation.

## Out of scope

This spec does not add request lifecycle hooks to serializers. Serializers are not a replacement for middleware.

This spec does not define TypeScript SDK changes, though it identifies a composition issue that likely applies to TypeScript serialization and encryption middleware.

This spec does not remove raw JSON mode. Strict JSON-only operation remains available through `serializer=None`.

## Risks

The serializer pipeline centralizes sensitive payload handling. Incorrect ordering could leak plaintext, fail to decrypt data, or return serialized marker shapes to user code.

Using `serializer=` for a chain is less literal than `serializers=`, but it preserves the existing public option name and keeps the Python-facing concept idiomatic.

## Open questions

- Should the SDK add a `serializers=` alias later for users who prefer plural naming when passing a sequence?

## Implementation

This is a v0.6 breaking behavior change. It should be coordinated with [`foundation/pydantic_serialization_by_default.md`](./pydantic_serialization_by_default.md), [`foundation/infer_output_types.md`](./infer_output_types.md), [`foundation/typed_event_input_data.md`](./typed_event_input_data.md), and [`foundation/rewrite_middleware.md`](./rewrite_middleware.md).

### Public API

Add a public payload serializer protocol or base class:

```python
T = typing.TypeVar("T")
MaybeAwaitable = T | typing.Awaitable[T]
PayloadSerializerStage = typing.Literal["application", "wire"]


class PayloadSerializer(typing.Protocol):
    stage: PayloadSerializerStage

    def serialize(
        self,
        value: object,
        ctx: PayloadSerializerContext,
    ) -> MaybeAwaitable[object]:
        ...

    def deserialize(
        self,
        value: object,
        ctx: PayloadSerializerContext,
    ) -> MaybeAwaitable[object]:
        ...
```

Serializer methods return the original value unchanged when the serializer does not apply. Exceptions are real serializer failures and stop the chain. v0.6 does not add an unsupported sentinel.

Serializer stages distinguish serializers that normalize application values from serializers that produce outer wire representations:

- `application`: Converts application values to and from JSON-compatible values. `PydanticSerializer` and custom model serializers use this stage.
- `wire`: Converts already JSON-compatible payloads to and from wire-boundary envelopes. `EncryptionSerializer`, compression, and large-payload externalization use this stage.

The public base class should default `stage` to `"application"` for custom serializer ergonomics. A serializer protocol implementation may expose the same value as an instance attribute, property, or class attribute.

Keep `serializer` on `Inngest(...)`:

```python
class Inngest:
    def __init__(
        self,
        *,
        app_id: str,
        serializer: PayloadSerializer
        | Sequence[PayloadSerializer]
        | None
        | Unset = UNSET,
        middleware: Sequence[type[Middleware]] | None = None,
        ...
    ) -> None: ...
```

Constructor normalization:

- Omitted `serializer` becomes `[PydanticSerializer()]`.
- `serializer=None` disables custom payload transformation.
- `serializer=MySerializer()` becomes `[MySerializer()]`.
- `serializer=[PydanticSerializer(), MySerializer(), EncryptionSerializer(...)]` preserves that order.
- The normalized sequence must be application-to-wire: every `application` serializer appears before every `wire` serializer. If a `wire` serializer is followed by an `application` serializer, fail construction with a clear ordering error.

### Context

Serializers should receive enough read-only context to make boundary decisions without becoming full lifecycle middleware:

```python
PayloadSerializerDirection = typing.Literal["serialize", "deserialize"]

PayloadSerializerBoundary = typing.Literal[
    "event_data",
    "function_output",
    "on_failure_output",
    "step_output",
    "step_memo",
    "invoke_input",
    "invoke_output",
    "wait_for_event_data",
]


@dataclasses.dataclass(frozen=True)
class PayloadSerializerContext:
    direction: PayloadSerializerDirection
    boundary: PayloadSerializerBoundary
    typ: object
    stage: PayloadSerializerStage
    path: tuple[str | int, ...] = ()
    event_name: str | None = None
    function: MiddlewareFunctionInfo | None = None
    step: MiddlewareStepInfo | None = None
```

The exact context fields can evolve, but the core contract should stay narrow:

- Boundary tells the serializer what kind of payload is crossing the boundary.
- Direction tells it whether it is serializing or deserializing.
- `typ` supplies the inferred or explicit target type when one exists.
- Stage tells the serializer whether it is running as an application normalizer or an outer wire transform.
- Path lets recursive helper serializers make field-level decisions.
- Function, step, and event metadata let policy serializers such as encryption or schema migration make scoped decisions.

Serializers should not receive `next`, mutate `ctx.ext`, wrap requests, observe retries, or handle cleanup. Those remain middleware responsibilities.

### Ordering

The SDK owns serializer ordering:

- Serialization runs serializers in the order provided by the user.
- Deserialization runs serializers in reverse order.
- The list is described as application-to-wire order.
- The constructor validates stage order so application serializers cannot be accidentally placed outside wire serializers.
- Encryption serializers should be placed after application serializers so encryption is the outer wire boundary.
- Async execution awaits awaitable serializer results. Sync execution rejects coroutine or otherwise awaitable serializer results with the same documented error shape as async middleware used from a sync execution path.

For example:

```python
serializer=[
    inngest.PydanticSerializer(),
    DateTimeSerializer(),
    inngest_encryption.EncryptionSerializer(key=...),
]
```

This produces:

```text
Outbound: raw Python -> Pydantic/date conversion -> encrypted envelope -> wire
Inbound: wire -> decrypted payload -> Pydantic/date restoration -> raw Python
```

### Boundary behavior

Apply serializers at every payload boundary currently handled by custom serialization or encryption middleware:

- Send-side event data
- Receive-side `ctx.event.data` and `ctx.events[*].data`
- Function output
- `on_failure` output
- `step.run` output
- Memoized step output returned to user code
- `step.invoke(function=..., data=...)` input
- `step.invoke_by_id(..., data=...)` input
- `step.invoke(function=...)` output
- Typed `step.wait_for_event()` data

Untyped round-trip outputs still use raw JSON semantics for type-preserving serializers. A serializer such as `PydanticSerializer` should no-op or fail clearly when `typ` is not usable for round-trip restoration. Wire-boundary serializers such as encryption may still serialize and deserialize untyped raw JSON-compatible values because they do not depend on the Python target type.

### Middleware interaction

Serializers and middleware have different responsibilities:

- Serializers transform payload values crossing the app/server boundary.
- Middleware observes, wraps, or mutates execution lifecycle behavior.

Application middleware should generally observe application-level values, not encrypted wire envelopes. Inbound payloads should be deserialized before function handlers and ordinary application middleware observe them. Outbound function and step outputs should pass through ordinary application middleware before payload serialization.

Send-side event middleware has a dedicated prepared-event boundary because event data has an object-shaped wire contract and existing middleware often expects mapping operations:

1. Normalize produced event objects.
2. Apply application-stage serializers needed to produce object-shaped JSON event data.
3. Run ordinary `transform_send_event` middleware.
4. Re-validate object-shaped event data.
5. Apply wire-stage serializers such as encryption.
6. Send the wire payload.

This preserves the mapping-shaped event-data assumption for send middleware while still keeping encryption at the outer boundary. Middleware sees prepared send-side `Event` objects with `data: dict[str, Any]`, not raw models or encrypted wire envelopes.

### Built-in serializers

Keep `PydanticSerializer` as the default built-in serializer.

`PydanticSerializer` should:

- Serialize Pydantic models and other supported typed values to JSON-compatible values.
- Deserialize typed receive-side and round-trip outputs using the inferred or explicit `typ`.
- No-op for raw JSON-compatible values when no type-aware restoration is needed.
- Fail clearly when typed restoration is required and custom serializer support is disabled or unavailable.

Update `pkg/inngest_encryption` to expose `EncryptionSerializer` for v0.6 compatibility. `EncryptionSerializer` should:

- Encrypt function and step outputs as whole payloads.
- Decrypt memoized function and step payloads before type restoration.
- Encrypt only the configured event-data field by default, such as `event.data.encrypted`.
- Apply the same event-data encryption policy to invoke payload data.
- Support decrypt-only mode and fallback keys.
- Preserve cross-language compatibility with the TypeScript encryption middleware envelope.

The staged encryption package release plan from [`foundation/rewrite_middleware.md`](./rewrite_middleware.md) still applies.

### Tests

Add serializer pipeline tests:

- Omitted `serializer` uses `[PydanticSerializer()]`.
- `serializer=None` disables custom payload transformation.
- A provided serializer sequence runs exactly in the provided order for serialization.
- The provided serializer sequence runs in reverse order for deserialization.
- Serialization followed by encryption round-trips for function output.
- Serialization followed by encryption round-trips for `step.run` output and memoized replay.
- Serialization followed by encryption round-trips for send-side event data and receive-side typed event data.
- Serialization followed by encryption round-trips for `step.invoke(function=..., data=...)`.
- Encryption remains the outer wire boundary, so the Inngest server only observes encrypted envelopes for encrypted payloads.
- Ordinary middleware does not receive encrypted envelopes unless a specific boundary explicitly documents that it does.
- Strict JSON-only mode with `serializer=None` keeps rejecting non-JSON-compatible values.

Add migration tests:

- `PydanticSerializer` remains the public Pydantic helper name.
- `EncryptionMiddleware` is not accepted as v0.6 middleware, or exists only as a migration alias that fails with a clear error.
- `EncryptionSerializer` composes with `PydanticSerializer` without leaking serialized marker shapes to user code.
