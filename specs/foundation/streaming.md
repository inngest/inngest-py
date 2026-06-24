# Replace `Streaming` enum with a FastAPI `streaming` option

Area: Config
Change type: Quality of life

## Problem

`Streaming` is exported publicly and passed to `fast_api.serve(...)`, but streaming is only meaningful for FastAPI. Other framework integrations pass `Streaming.DISABLE` internally because they do not support streaming responses.

The enum makes a narrow FastAPI feature look like a cross-framework public concept.

## Solution

Remove the public `Streaming` enum. Use `streaming: bool | None = None` on `fast_api.serve(...)` only.

Framework integrations that do not support streaming should not expose a `streaming` parameter.

FastAPI streaming configuration should keep environment fallback:

- `streaming=True` enables streaming.
- `streaming=False` disables streaming and ignores `INNGEST_STREAMING`.
- `streaming=None` reads `INNGEST_STREAMING`.
- If `streaming=None` and `INNGEST_STREAMING` is unset, streaming defaults to disabled.

Non-FastAPI integrations should always resolve streaming to disabled internally. `INNGEST_STREAMING` must not affect Flask, Django, Tornado, DigitalOcean, or Connect.

## Related work

### Blocking

None.

### Non-blocking

[`foundation/separate_logging.md`](./separate_logging.md) defines the SDK logger hierarchy used for streaming environment warnings.

[`foundation/sdk_log_extra_fields.md`](./sdk_log_extra_fields.md) defines the namespaced `extra` field convention used by those warnings.

## Out of scope

This does not add streaming support to non-FastAPI integrations.

## Risks

This is a small breaking API change for FastAPI users who currently import or pass `inngest.Streaming`. The replacement is straightforward, but release notes should call it out explicitly.

## Implementation

```python
# Before
inngest.fast_api.serve(
    app,
    client,
    functions,
    streaming=inngest.Streaming.FORCE,
)

# After
inngest.fast_api.serve(
    app,
    client,
    functions,
    streaming=True,
)
```

The FastAPI public signature becomes:

```python
def serve(
    app: fastapi.FastAPI,
    client: inngest.Inngest,
    functions: list[inngest.Function],
    *,
    path: str = const.DEFAULT_SERVE_PATH,
    streaming: bool | None = None,
) -> None:
    ...
```

`None` is the only public API value that enables env fallback. Explicit booleans always win over `INNGEST_STREAMING`.

### Internal contract

`CommHandler` should accept `streaming: bool | None`, not `const.Streaming | None`.

`CommHandler` should own env var resolution:

```python
if streaming is None:
    streaming_enabled = env_lib.get_streaming_enabled(default=False)
else:
    streaming_enabled = streaming is True
```

FastAPI should pass the public `streaming` argument through to `CommHandler`, preserving `None` as the default so `INNGEST_STREAMING` remains available.

Framework integrations that cannot support streaming should pass `streaming=False` to `CommHandler`. This explicitly disables streaming and prevents `INNGEST_STREAMING` from enabling an unsupported streaming response shape.

Remove `const.Streaming` entirely. Also remove the public `inngest.Streaming` import and `__all__` export.

### Boolean handling

`streaming` is a typed Python API. The SDK should not support string values, integers, old `Streaming` enum values, or other invalid Python inputs passed to `fast_api.serve(streaming=...)`.

Add targeted runtime validation at the FastAPI public boundary. If `streaming` is not exactly `True`, `False`, or `None`, fail with a migration-friendly `TypeError`:

```text
streaming must be bool | None. Use streaming=True instead of inngest.Streaming.FORCE, and streaming=False instead of inngest.Streaming.DISABLE.
```

This validation should explicitly reject `bool`-adjacent values such as `1`, `0`, `"true"`, `"false"`, and old enum-style values. Do not use truthiness to resolve the option. The final enabled value should be derived with explicit boolean identity, such as `streaming is True`, after env fallback has been handled.

### Env var compatibility

`INNGEST_STREAMING` should use boolean string values as the canonical v0.6 form:

- `true` and `1` enable streaming.
- `false`, `0`, and an empty string disable streaming.
- An unset env var uses the caller-provided default, normally disabled.

Keep the old enum-style env values for backward compatibility in v0.6:

- `force` enables streaming and logs an SDK deprecation warning.
- `allow` enables streaming and logs an SDK deprecation warning.
- `disable` disables streaming and logs an SDK deprecation warning.

Unrecognized values should log an SDK warning and resolve to disabled. Do not silently treat arbitrary non-empty strings as enabled.

`INNGEST_STREAMING` warnings should be emitted through `logging.getLogger("inngest.sdk.comm.streaming")` because `CommHandler` owns streaming resolution. Deprecated enum-style values should log a deprecation warning. Unrecognized values should log a warning.

Warnings should follow the SDK namespaced `extra` convention:

```python
logger.warning(
    "Invalid INNGEST_STREAMING value; streaming remains disabled",
    extra={
        "inngest_env_var": "INNGEST_STREAMING",
        "inngest_env_value": raw_value,
    },
)
```

The deprecation warning for `force`, `allow`, and `disable` should use the same `extra` keys and explain that `true` and `false` are the canonical v0.6 values.

### Connect behavior

Connect does not use framework HTTP response streaming, so it is not limited by the same response-shape constraints as Flask, Django, Tornado, or DigitalOcean.

`INNGEST_STREAMING` still must not affect Connect. Connect has its own bidirectional worker transport and should not read or propagate the FastAPI-only streaming setting. Any future Connect streaming or chunking behavior should be configured separately from `fast_api.serve(streaming=...)` and `INNGEST_STREAMING`.

### Tests

Update `tests/test_inngest/test_serve/test_streaming.py` and `tests/test_inngest/test_server_timings/test_fast_api.py` to use `streaming=True` and `streaming=False` instead of `inngest.Streaming.FORCE` and `inngest.Streaming.DISABLE`.

Add coverage for:

- `fast_api.serve(streaming=True)` enables streaming.
- `fast_api.serve(streaming=False)` disables streaming and ignores `INNGEST_STREAMING`.
- `fast_api.serve(streaming=inngest.Streaming.FORCE)` is no longer possible through public imports, and enum-like invalid values fail with the migration-friendly `TypeError`.
- `fast_api.serve(streaming=1)`, `fast_api.serve(streaming=0)`, and `fast_api.serve(streaming="true")` fail with the migration-friendly `TypeError`.
- Omitted `streaming` preserves env fallback.
- Omitted `streaming` with no `INNGEST_STREAMING` disables streaming.
- `INNGEST_STREAMING=true` and `INNGEST_STREAMING=1` enable streaming.
- `INNGEST_STREAMING=false`, `INNGEST_STREAMING=0`, and an empty `INNGEST_STREAMING` disable streaming.
- `INNGEST_STREAMING=force`, `INNGEST_STREAMING=allow`, and `INNGEST_STREAMING=disable` keep their old behavior and log SDK deprecation warnings.
- Unrecognized `INNGEST_STREAMING` values log an SDK warning and resolve to disabled.
- Deprecation and invalid-value warnings are emitted through `inngest.sdk.comm.streaming`.
- Deprecation and invalid-value warnings use namespaced `extra` fields, including `inngest_env_var` and `inngest_env_value`.
- `INNGEST_STREAMING` cannot enable streaming for Flask, Django, Tornado, DigitalOcean, or Connect.
- Connect does not read or propagate `INNGEST_STREAMING`.
- `inngest.Streaming` is no longer exported.
- `CommHandler` resolves streaming to a plain `bool` before checking whether to create a streaming response.

### Documentation

Update `pkg/inngest/docs/REQUEST_LIFECYCLE.md` to describe streaming as a FastAPI-only response mode.

Document `INNGEST_STREAMING=true` and `INNGEST_STREAMING=false` as the canonical env values. Mention `force`, `allow`, and `disable` only as deprecated v0.6 compatibility values.

Update the FastAPI `serve()` docstring to describe `streaming: bool | None`:

- `True` enables streaming.
- `False` disables streaming and ignores `INNGEST_STREAMING`.
- `None` uses `INNGEST_STREAMING`, defaulting to disabled when unset.

The docstring should also state that streaming is only supported by the FastAPI integration. Other framework integrations ignore `INNGEST_STREAMING` because they cannot produce the required streaming response shape.
