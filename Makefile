format:
	@uv run ruff format .

format-check:
	@uv run ruff format --check .

install:
	@uv sync --all-extras

itest:
	@cd pkg/inngest && make itest
	@cd pkg/inngest_encryption && make itest

pre-commit: format-check lint type-check utest

lint:
	@cd examples && make lint
	@cd pkg/inngest && make lint
	@cd pkg/inngest_encryption && make lint
	@cd pkg/test_core && make lint

type-check:
	@cd examples && make type-check
	@cd pkg/inngest && make type-check
	@cd pkg/inngest_encryption && make type-check
	@cd pkg/test_core && make type-check
	@uv run mypy --config-file=mypy.ini tests

utest:
	@cd pkg/inngest && make utest
	@cd pkg/inngest_encryption && make utest
