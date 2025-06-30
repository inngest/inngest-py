# Inngest SDK Package

## Package Overview

This is the primary package in this monorepo. It's the Python SDK for the Inngest platform.

Its purpose is to add Inngest "worker" logic into users' apps. Users can run these apps anywhere they like (Inngest does not sell compute).

**Key Features:**

- Event-driven
- Steps are invididually-retryable units of work
- Framework-agnostic design (e.g. Flask). Framework-specific code is limited to individual files (e.g. `flask.py`)
- Support both async and sync code
- Built-in middleware system
- Excellent static type safety

## Development Environment

**Prerequisites:**

- Python 3.10+ (minimum supported version)
- Dependencies installed from monorepo root: `make install`

**Package Structure:**

## Development Commands

All commands must be run from the `pkg/inngest/` directory:

**Setup & Dependencies:**

```bash
cd pkg/inngest
# Dependencies are installed from monorepo root
```

**Code Quality:**

```bash
make format      # Auto-format (use from monorepo root)
make lint        # Lint with ruff
make type-check  # Type check with mypy
```

**Testing:**

```bash
make itest  # Run integration tests. Tests live in `tests/test_inngest` (relative to the monorepo root)
make utest  # Run unit tests. Tests live next to the code they test
```

**Build & Release:**

Do not consider building and releasing. This is automatically done in CI.

## Architecture Guidelines

**Public API Design:**

Anything is considered public if it isn't within an `_internal` directory.

Each file and directory within `inngest` is meant to be imported separately. This separation is to avoid forcing users to install dependencies they don't need. The import entrypoints are:

- `__init__.py` - Core
- `connect` - Inngest Connect (expose via WebSocket, as opposed to HTTP with `serve`)
- `digital_ocean.py` - DigitalOcean integration
- `django.py` - Django integration
- `fast_api.py` - FastAPI integration
- `flask.py` - Flask integration
- `tornado.py` - Tornado integration

Additionally, there's an `experimental` directory. This directory is for features whose behavior and/or API are not stable. Nothing in this directory is subject to semver guarantees.

**Framework Integration Pattern:**

- Framework-specific code must never be within `inngest/_internal`.
- Each framework file must provide a `serve` function, which is used to expose Inngest functions to HTTP requests.
- The `serve` function is reponsible for normalizing requests and denormalizing responses.

**Async/Sync Duality:**

- Functions can be async or sync. Both are supported.

**Error Handling:**

- Internal errors are returned, not raised.
- Errors that leave internal code (i.e. make their way to userland code) are raised, not returned.
- Errors with an `Interrupt` suffix are for control flow interruption and should not be thought of as "errors" in the traditional sense.

## Testing Patterns

**Unit Tests:**

- Next to the code they test.
- Test individual components in isolation.

**Integration Tests:**

- In `tests/test_inngest` (relative to the monorepo root)
- Strive to only test the public API. Exceptions can be OK.

## Key Dependencies

**Dependencies:**

Minimize the number of dependencies.
