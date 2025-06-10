# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

To run a command in a specific package, `cd` into it first (e.g. `cd pkg/inngest && make utest`).

**Setup:**

```bash
make install  # Install dependencies
```

**Code Quality:**

```bash
make format         # Auto-format
make lint           # Lint all packages
make type-check     # Type check all packages
cd pkg/inngest && make lint  # Lint a specific package
```

**Testing:**

```bash
make itest  # Run integration tests
make utest  # Run unit tests
cd pkg/inngest && make itest  # Run integration tests for a specific package
pytest tests/test_inngest/test_function/test_fast_api.py -v  # Run a specific test file
```

## Architecture

**Monorepo Structure:**

- `examples/` - Framework integration examples
- `pkg/` - Packages. Subdirectories are for each package
  - `inngest/` - Core SDK (published to PyPI)
  - `inngest_encryption/` - Encryption middleware (published to PyPI)
  - `test_core/` - Test utilities (not published to PyPI)
- `tests/` - Integration tests using case-based organization. Subdirectories are for each package

**Package Structure:**

- `__init__.py` - Public API for the package
- `README.md` - Visible in PyPI (if package is published)

**Core Package Internal Structure (`pkg/inngest`):**

- `comm_lib/` - Framework-agnostic communication layer
- `middleware_lib/` - Middleware system
- `server_lib/` - Things that Inngest servers are opinionated about (e.g. request schemas)
- Framework specific code is in dedicated files (e.g. `flask.py`).

**Key Concepts:**

- **Event-driven Functions**: Functions triggered by events with data payloads
- **Step-based Execution**: Functions contain multiple steps that retry independently
- **Async/Sync Duality**: Supports both async and sync functions
- **Framework Agnostic**: Same function code works across all frameworks

## Testing Patterns

Tests use case-based organization in `tests/test_inngest/test_function/cases/` where each case represents a specific scenario (e.g., `parallel_steps.py`, `invoke_failure.py`, `wait_for_event_timeout.py`).

## Requirements

- Python 3.10+ minimum
- Framework versions: FastAPI ≥0.110.0, Flask ≥3.0.0, Django ≥5.0, Tornado ≥6.4
