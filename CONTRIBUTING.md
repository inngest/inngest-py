## Setup

```sh
python -m venv .venv && source .venv/bin/activate
make install
```

## Start Example Servers

```sh
# Flask
(cd examples/flask && make dev)

# Tornado
(cd examples/tornado && make dev)
```

## Testing

Run before committing:

```sh
make precommit
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

# Integration tests (don't start Dev Server)
(export DEV_SERVER_ENABLED=0 && make itest)

# Integration tests (start Dev Server on a specific port)
(export DEV_SERVER_PORT=9123 && make itest)
```
