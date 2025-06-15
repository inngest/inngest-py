# Test Core Package

## Package Overview

This package provides shared testing utilities for the monorepo. It contains common test infrastructure, helpers, and patterns used across integration tests in the monorepo.

## Development Commands

All commands must be run from the `pkg/test_core/` directory:

**Code Quality:**

```bash
make format      # Auto-format (use from monorepo root)
make lint        # Lint with ruff
make type-check  # Type check with mypy
```

**Testing:**

No dedicated tests - this package provides utilities for other tests.

**Build & Release:**

This package is NOT published to PyPI. It's internal tooling only.
