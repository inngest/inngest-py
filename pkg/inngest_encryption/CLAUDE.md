# Inngest Encryption Package

## Package Overview

This package provides encryption middleware for the Inngest Python SDK. It enables automatic encryption and decryption of sensitive data in Inngest functions and events.

**Key Features:**

- Symmetric encryption using PyNaCl (libsodium)
- Automatic encryption of event data, step output, and function output
- Key rotation support with fallback decryption keys
- Selective field encryption (only encrypts `encrypted` field by default)
- Compatible with all Inngest framework integrations

## Development Environment

**Prerequisites:**

- Python 3.10+ (minimum supported version)
- Dependencies installed from monorepo root: `make install`

**Package Structure:**

```
pkg/inngest_encryption/
├── inngest_encryption/           # Main package code
│   ├── __init__.py              # Public API exports
│   ├── main.py                  # EncryptionMiddleware implementation
│   ├── _internal/               # Internal implementation
│   │   └── strategies/          # Future: Multiple encryption strategies
│   └── py.typed                 # Type information marker
├── README.md                    # Package documentation (visible on PyPI)
└── pyproject.toml              # Package configuration
```

## Development Commands

All commands must be run from the `pkg/inngest_encryption/` directory:

**Code Quality:**

```bash
make format      # Auto-format (use from monorepo root)
make lint        # Lint with ruff
make type-check  # Type check with mypy
```

**Testing:**

```bash
make itest  # Run integration tests. Tests live in `tests/test_inngest_encryption` (relative to the monorepo root)
make utest  # Run unit tests. Tests live next to the code they test
```

**Build & Release:**

Do not consider building and releasing. This is automatically done in CI.

## Architecture Guidelines

**Public API Design:**

Anything is considered public if it isn't within an `_internal` directory.

**Encryption Strategy:**

- Uses PyNaCl (libsodium) for symmetric encryption
- Strategy identifier: `"inngest/libsodium"`
- Encryption markers: `__ENCRYPTED__` and `__STRATEGY__`
- Default encryption field: `"encrypted"`

**Middleware Pattern:**

- Extends `inngest.MiddlewareSync` base class
- Implements middleware hooks: `before_send_events`, `transform_input`, `transform_output`
- Factory pattern for easy instantiation

## Key Dependencies

**Dependencies:**

Minimize the number of dependencies.
