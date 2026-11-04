# Inngest LangChain Package

## Package Overview

This package makes LangChain agents durable in Inngest functions. It's `create_agent` middleware that runs each model call and tool call that reaches it as an Inngest step.

**Key Features:**

- One `InngestMiddleware` class for sync (`ContextSync`, `agent.invoke`) and async (`Context`, `agent.ainvoke`) functions; the ctx type picks the mode
- `durable(agent)` sets `max_concurrency=1` and rejects the agent's own checkpointer; the middleware's `before_agent` re-checks both from the run config
- Step IDs: `<agent_id>/model-<n>` (per-instance call ordinal) and `<agent_id>/tool-<percent-encoded tool call ID>`
- Parallel tool calls run one at a time via `max_concurrency=1`; once a step ends the request, later steps of the instance re-raise that interrupt
- Steps grouped under an automatic agent span through the experimental `ctx.group._span`

## Development Environment

**Prerequisites:**

- Python 3.10+ (minimum supported version)
- Dependencies installed from monorepo root: `make install`

**Package Structure:**

```
pkg/inngest_langchain/
├── inngest_langchain/            # Main package code
│   ├── __init__.py               # Public API exports
│   ├── _internal/                # Internal implementation
│   │   ├── const.py              # VERSION and the span/step ORIGIN
│   │   ├── middleware.py         # InngestMiddleware and durable()
│   │   ├── step_output.py        # Stored step format, incl. structured output
│   │   └── fixtures/steps/       # Stored step JSON pinned by step_output_test.py
│   └── py.typed                  # Type information marker
├── README.md                     # Package documentation (visible on PyPI)
└── pyproject.toml                # Package configuration
```

## Development Commands

All commands must be run from the `pkg/inngest_langchain/` directory:

**Code Quality:**

```bash
make format      # Auto-format (use from monorepo root)
make lint        # Lint with ruff
make type-check  # Type check with mypy
```

**Testing:**

```bash
make itest  # Run integration tests. Tests live in `tests/test_inngest_langchain` (relative to the monorepo root)
make utest  # Run unit tests. Tests live next to the code they test
```

**Build & Release:**

Do not consider building and releasing. This is automatically done in CI.

## Architecture Guidelines

**Public API Design:**

Anything is considered public if it isn't within an `_internal` directory. Only `InngestMiddleware` and `durable` are exported.

**Modes:**

- Every hook checks the ctx type and raises `NonRetriableError` in the wrong mode.
- `before_agent`/`abefore_agent` take `config: Optional[RunnableConfig]`, which LangGraph injects only if it recognises the annotation string; keep it `Optional[...]`, not `| None`.

**Retries:**

- Inngest owns retries. `ModelRetryMiddleware` and `ToolRetryMiddleware` are documented as unsupported, not detected. `ModelFallbackMiddleware` is supported: the fallback is the next model step.

**Stored step format:**

- Unreleased: change it freely, keep `v` at 1, and regenerate the fixtures.
- After the first release, runs in flight replay it after a deploy: any change bumps `v`, and the reader keeps accepting the previous `v` for at least one release.

**Experimental SDK API:**

- `ctx.group._span` is private and can change in any `inngest` release. The package checks for it on import.
- There's no upper bound on `inngest`; CI also runs the unit tests against the latest `inngest` release.

## Key Dependencies

**Dependencies:**

Minimize the number of dependencies.
