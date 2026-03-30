# Inngest SDK Package

## Package Overview

Refer to `CONTRIBUTING.md`.

**Key Features:**

- Event-driven
- Steps are individually-retryable units of work
- Framework-agnostic design (e.g. Flask). Framework-specific code is limited to individual files (e.g. `flask.py`)
- Support both async and sync code
- Built-in middleware system
- Excellent static type safety

## Development Environment

Refer to `CONTRIBUTING.md`.

**Build & Release:**

Do not consider building and releasing. This is automatically done in CI.

## Architecture Guidelines

Refer to `CONTRIBUTING.md`.

**Internal docs** in `docs/` explain high-level SDK behavior:

- `docs/REQUEST_LIFECYCLE.md` - How requests flow from Inngest server through the SDK
- `docs/EXECUTION_MODEL.md` - Deterministic replay, steps, memoization, parallel execution
- `docs/AUTH.md` - Signing keys, request/response verification, key rotation
- `docs/INSPECTION.md` - GET endpoint responses (authenticated vs unauthenticated)
- `docs/SYNC.md` - Function registration (in-band, out-of-band, Connect)
- `docs/CONNECT.md` - WebSocket-based Connect protocol (high-level)

## Testing Patterns

Refer to `CONTRIBUTING.md`.

## Key Dependencies

**Dependencies:**

Minimize the number of dependencies.
