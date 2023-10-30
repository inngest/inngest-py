## Setup

```sh
python -m venv .venv && source .venv/bin/activate
make install
```

## Start Example Servers

```sh
# Fast API
(cd examples/fast_api && make dev)

# Flask
(cd examples/flask && make dev)

# Tornado
(cd examples/tornado && make dev)
```

## Testing

Run before committing:

```sh
make pre-commit
```

Run things individually:

```sh
make format-check
make lint
make type-check
make utest

# Changes code
make format

# Unit tests
make utest

# Integration tests
make itest
```

When running `make itest`, there are some optional env vars:

```sh
# Disable (when you want to use an already-running Dev Server)
DEV_SERVER_ENABLED=0

# Specify port (uses a random available port by default)
DEV_SERVER_PORT=9000

# Show Dev Server stdout and stderr
DEV_SERVER_VERBOSE=1
```

# Architecture

## Internal modules

> ℹ️ Some modules have a `_lib` suffix. The only purpose of this suffix is to avoid collisions with common variable names.

- `client_lib`: Inngest client, which users can use to send events.
- `comm`: Framework agnostic communication layer between the Executor and functions.
- `env`: Stuff related to the runtime environment.
- `function`: Data structure for the user's functions.
- `net`: General networking stuff. Should not have business logic.
- `result`: Wrapper types for writing Rust-like errors-as-values code. Will probably expand its use.
- `types`: Low-level primitives for type annotations. Should not have business logic.
