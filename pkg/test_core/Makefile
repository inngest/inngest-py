export MYPYPATH=../inngest

.PHONY: lint
lint:
	@uv run ruff check .

.PHONY: lint-fix
lint-fix:
	@uv run ruff check . --fix

.PHONY: type-check
type-check:
	@uv run mypy --config-file=../../mypy.ini .
