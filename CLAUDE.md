# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

Refer to `CONTRIBUTING.md`.

- **Always use `uv` to run Python tools** (e.g. `uv run pytest`, `uv run mypy`). Never use `python -m`, `.venv/bin/`, or bare `pytest`.

## Architecture

Refer to `CONTRIBUTING.md`.

## Testing Patterns

Tests use case-based organization in `tests/test_inngest/test_function/cases/` where each case represents a specific scenario (e.g., `parallel_steps.py`, `invoke_failure.py`, `wait_for_event_timeout.py`).

## Code Review

- The `_internal` package and `_`-prefixed names are private by default. However, symbols defined in `_internal` may be re-exported by a public module above it — in that case they are part of the public API. Check the re-export chain before deciding whether a change is user-facing.

## Requirements

- Python 3.10+ minimum
