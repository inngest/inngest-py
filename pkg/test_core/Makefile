export MYPYPATH=../inngest

.PHONY: lint
lint:
	@uv run ruff check .

.PHONY: type-check
type-check:
	@uv run mypy --config-file=../../mypy.ini .
