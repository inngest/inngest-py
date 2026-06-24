# Rename `is_production` to `is_dev`

Area: Config
Change type: Quality of life

## Problem

`Inngest(is_production=False)` opts into dev-server mode. The internal model is already closer to "cloud vs dev server", but the public API exposes it as a negated production flag.

The name is easy to invert mentally because `False` is the value used for local development. The client also exposes a vestigial public `is_production` attribute that encourages callers to branch on internal SDK mode.

## Solution

Remove `is_production` and replace it with `is_dev: bool | None = None`. The new name directly describes the behavior users are selecting: dev mode.

```python
# Before
client = inngest.Inngest(app_id="app", is_production=False)

# After
client = inngest.Inngest(app_id="app", is_dev=True)
```

This is a breaking constructor change in v0.6. The SDK will not accept `is_production` as a deprecated alias. Calls that still pass `is_production` fail with the normal Python unexpected-keyword-argument error.

## Related work

### Blocking

None.

### Non-blocking

None.

## Out of scope

This does not add a new public mode-inspection API or change the underlying cloud/dev server mode model.

## Risks

Mode selection affects security behavior, default server URLs, and request validation. This is an intentional breaking change, and migration messaging must make the boolean inversion obvious: `is_production=False` becomes `is_dev=True`.

## Implementation

`is_dev` controls SDK mode:

- `is_dev=True` forces dev mode.
- `is_dev=False` forces cloud mode.
- `is_dev=None` preserves auto-detection from environment variables.

The client stores the resolved value internally as `self._is_dev: bool`. This private boolean means Dev Server behavior is active. `False` means cloud-compatible behavior, including both Inngest Cloud and self-hosted backends.

Migration mapping:

| Old | New |
| --- | --- |
| `is_production=True` | `is_dev=False` |
| `is_production=False` | `is_dev=True` |
| `is_production=None` | `is_dev=None` |
| Omitted | Omitted |

Because `is_production` is removed from the constructor, there is no dual-argument behavior to define. Any call containing both `is_dev` and `is_production` is invalid because `is_production` is invalid.

Dev mode removes production security requirements such as normal request signing, changes the default Inngest API and Event API origins to the Dev Server, and makes the SDK accept Dev Server traffic. Non-dev mode keeps production request validation and cloud-compatible defaults.

`is_dev=True` controls security behavior regardless of which API URLs are configured. If a user sets `is_dev=True` while also passing explicit `api_base_url` or `event_api_base_url` values that do not point at the default Dev Server, the SDK still runs in dev mode: request signing requirements are relaxed and Dev Server traffic is accepted. That combination is valid for tests and custom local environments, but it must be visibly intentional. Self-hosted production-compatible backends should use `is_dev=False` or auto-detected non-dev mode with explicit API URLs.

`is_dev` is the constructor equivalent of `INNGEST_DEV`:

- `INNGEST_DEV=true` or `INNGEST_DEV=1` enables dev mode and uses the default Dev Server URL.
- `INNGEST_DEV=false`, `INNGEST_DEV=0`, or an empty value disables dev mode.
- `INNGEST_DEV=<url>` enables dev mode and uses that URL as the default API and Event API origin.

For `INNGEST_DEV=<url>`, trim surrounding whitespace before parsing. A value is a valid URL only if it has an `http` or `https` scheme and a non-empty hostname. `localhost:8288` without a scheme is invalid. Query strings and fragments are invalid for this setting. Normalize accepted URLs by removing trailing slashes from the full base URL, so `http://localhost:8288/` becomes `http://localhost:8288` and `http://localhost:8288/dev/` becomes `http://localhost:8288/dev`.

### Mode precedence

The constructor argument takes precedence for mode selection. If `is_dev` is `True` or `False`, `INNGEST_DEV` must not change the selected mode.

Mode selection order:

- `is_dev=True` forces dev mode.
- `is_dev=False` forces non-dev mode.
- `is_dev=None` infers mode from `INNGEST_DEV`.

When `is_dev=None`, `INNGEST_DEV=true`, `INNGEST_DEV=1`, or `INNGEST_DEV=<url>` enables dev mode. `INNGEST_DEV=false`, `INNGEST_DEV=0`, an empty value, an unset value, or an unrecognized value disables dev mode.

Environment variable parsing must fail closed for mode detection. After trimming whitespace and lowercasing, only `true`, `1`, and valid URLs enable dev mode. `false`, `0`, empty, unset, and unrecognized values select non-dev mode. For non-empty unrecognized values, the SDK should log a warning that names `INNGEST_DEV`, reports the invalid value, and explains that dev mode remains disabled.

### URL precedence

URL resolution is separate from mode selection.

API URL precedence:

- `api_base_url`
- `INNGEST_API_BASE_URL`
- `INNGEST_BASE_URL`
- `INNGEST_DEV`, only when `self._is_dev` is `True` and `INNGEST_DEV` contains a URL
- Mode default

Event API URL precedence:

- `event_api_base_url`
- `INNGEST_EVENT_API_BASE_URL`
- `INNGEST_BASE_URL`
- `INNGEST_DEV`, only when `self._is_dev` is `True` and `INNGEST_DEV` contains a URL
- Mode default

When `self._is_dev` is `True`, the mode default is the Dev Server origin. When `self._is_dev` is `False`, the mode defaults are the Cloud API and Event API origins.

When `is_dev=False`, ignore `INNGEST_DEV` completely, including URL values and invalid values. Do not warn about invalid `INNGEST_DEV` values in this case because the constructor explicitly disables dev mode. A URL value in `INNGEST_DEV` is a dev-mode URL shortcut, not a general URL override. Users who want custom cloud or self-hosted origins should use `api_base_url`, `event_api_base_url`, `INNGEST_API_BASE_URL`, `INNGEST_EVENT_API_BASE_URL`, or `INNGEST_BASE_URL`.

When `is_dev=True`, `INNGEST_DEV` must not affect mode selection. If `INNGEST_DEV` contains a valid URL, use it according to the URL precedence above. If it contains a non-empty unrecognized value, log a warning and use the default Dev Server origin unless a higher-precedence URL source is set.

Remove the public `client.is_production` attribute; callers should not branch on the SDK's internal server mode. Internal uses must migrate to `self._is_dev` before the attribute is deleted. In particular, `CommHandler` must check `not client._is_dev` when deciding whether a missing signing key is an error, preserving the current behavior where non-dev requests require signing-key validation and Dev Server requests may be served unsigned.

### Tests

Add acceptance tests for mode selection:

- `is_dev=True` forces dev mode.
- `is_dev=False` forces non-dev mode.
- `is_dev=None` reads `INNGEST_DEV`.
- `INNGEST_DEV=true`, `INNGEST_DEV=1`, and `INNGEST_DEV=<url>` enable dev mode.
- `INNGEST_DEV=false`, `INNGEST_DEV=0`, an empty value, an unset value, and invalid non-empty values select non-dev mode.
- Invalid non-empty `INNGEST_DEV` values log a warning when they are considered.

Add acceptance tests for URL precedence:

- Constructor `api_base_url` and `event_api_base_url` override every environment URL.
- `INNGEST_API_BASE_URL` and `INNGEST_EVENT_API_BASE_URL` override `INNGEST_BASE_URL`.
- `INNGEST_BASE_URL` overrides an `INNGEST_DEV` URL.
- `INNGEST_DEV` URL is used only when `self._is_dev` is `True`.
- `is_dev=False` ignores every `INNGEST_DEV` value, including URL and invalid values.
- `INNGEST_DEV` URL parsing trims whitespace and accepts only `http` or `https` URLs with a hostname.
- `INNGEST_DEV=localhost:8288`, URLs with query strings, and URLs with fragments are invalid.
- Accepted `INNGEST_DEV` URLs are normalized by removing trailing slashes.

Add acceptance tests for security-sensitive behavior:

- Non-dev sending requires an event key.
- Dev sending uses the Dev Server event-key fallback.
- Non-dev serving requires signing-key validation.
- Dev serving accepts unsigned Dev Server traffic.
- Server-kind mismatch rejection is unchanged.
- `is_dev=True` still enables dev-mode security behavior when constructor or environment URL overrides point somewhere other than the default Dev Server.

### Public surface updates

Update repository-wide public references as part of the implementation:

- README examples.
- Package README examples.
- Constructor docstrings.
- Type-analysis fixtures such as `tests/test_inngest/test_types.py`.
- Auth, connect, serve, introspection, serialization, encryption, and framework integration tests.
- Any docs or comments that mention "production mode" or `is_production`.

Examples and tests should use `is_dev=True` for Dev Server behavior and `is_dev=False` for non-dev behavior. Avoid introducing a public runtime mode-inspection attribute to replace `client.is_production`.

Add public-surface regression coverage that no replacement mode-inspection attribute is introduced. Internal tests may inspect `_is_dev`, but public docs, examples, type fixtures, and user-facing API tests should not teach users to branch on SDK mode.
