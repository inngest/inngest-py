export MYPYPATH=../pkg/inngest:../pkg/inngest_encryption:../pkg/test_core

.PHONY: lint
lint:
	@uv run ruff check .

.PHONY: type-check
type-check:
	@uv run mypy --config-file=../mypy.ini .

.PHONY: type-check-pyright
type-check-pyright:
	@uv run pyright --project=../pyrightconfig.json .
