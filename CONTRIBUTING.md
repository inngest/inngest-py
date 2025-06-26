## Setup

```sh
make install
```

## Start example servers

```sh
# DigitalOcean
(cd examples/digital_ocean && make dev)

# Django
(cd examples/django && make dev)

# FastAPI
(cd examples/fast_api && make dev)

# Flask
(cd examples/flask && make dev)

# Tornado
(cd examples/tornado && make dev)
```

## Test

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

# Publish

Change the package version in the package's `pyproject.toml` (e.g. `pkg/inngest/pyproject.toml`).

Set the `VERSION` env var and run the `release` make target for the package. For example, the following command releases version `1.2.3` of the `inngest` package:

```sh
(cd pkg/inngest && export VERSION=1.2.3 && make release)
```

This will start CI for the tag, including publishing to PyPI.

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

# Troubleshooting

Kill orphaned Dev Servers using `kill -9 $(pgrep inngest-cli)`.
