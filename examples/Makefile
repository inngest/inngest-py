export MYPYPATH=../pkg/inngest:../pkg/inngest_encryption:../pkg/test_core

.PHONY: lint
lint:
	@uv run ruff check .

.PHONY: lint-fix
lint-fix:
	@uv run ruff check . --fix

.PHONY: type-check
type-check:
	@uv run mypy --config-file=../mypy.ini ./connect
	@uv run mypy --config-file=../mypy.ini ./digital_ocean
	@uv run mypy --config-file=../mypy.ini ./django
	@uv run mypy --config-file=../mypy.ini ./fast_api
	@uv run mypy --config-file=../mypy.ini ./flask
	@uv run mypy --config-file=../mypy.ini ./tornado
