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

## Test

Run all the things:

```sh
make precommit
```

Run things individually:

```sh
make format
make lint
make test
make type-check
```
