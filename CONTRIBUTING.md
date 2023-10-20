## Setup

1. `python -m venv .venv && source .venv/bin/activate`
1. `pip install '.[extra]' -c constraints.txt`

## Start Example Servers

```sh
# Flask
(cd examples/framework-flask && make dev)
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
make type-check
```
