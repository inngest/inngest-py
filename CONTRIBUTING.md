## Development Commands

Common commands are saved in `Makefile`s:

- The top-level `Makefile` is used for "whole monorepo" commands (e.g. linting the entire monorepo).
- Each package has its own `Makefile` for package-specific commands. To run a command in a specific package, `cd` into it first (e.g. `cd pkg/inngest && make lint`).

If running a custom command (i.e. not using `make`), use `uv`.

**Setup:**

```bash
make install  # Install dependencies
```

**Code Quality:**

```bash
# Auto-format all packages
make format

# Lint all packages
make lint

# Type check all packages
make type-check

# Lint a specific package
cd pkg/inngest && make lint
```

**Testing:**

```bash
# Run integration tests for all packages
make itest

# Run unit tests for all packages
make utest

# Run integration tests for a specific package
cd pkg/inngest && make itest

# Run a specific test
uv run pytest tests/test_inngest/test_function/test_fast_api.py::TestFunctions::test_crazy_ids -v
```

## Architecture

**Monorepo Structure:**

- `examples/` - Framework examples
- `pkg/` - Packages. Subdirectories are for each package
  - `inngest/` - Core SDK (published to PyPI)
  - `inngest_encryption/` - Encryption middleware (published to PyPI)
  - `test_core/` - Test utilities (not published to PyPI)
- `tests/` - Integration tests using case-based organization. Subdirectories are for each package

**Testing:**

- Strive to make tests as "real" as possible.
  - In other words, it's usually better for tests to look like userland code.
  - This often means testing via an Inngest functions.
- Unit tests are usually discouraged but can be valuable.
  - For example, testing myriad edge cases in a pure function.
