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
	@cd tests && make lint

type-check:
	@cd examples && make type-check
	@cd pkg/inngest && make type-check
	@cd pkg/inngest_encryption && make type-check
	@cd pkg/test_core && make type-check
	@cd tests && make type-check

type-check-pyright:
	@cd tests && make type-check-pyright

utest:
	@cd pkg/inngest && make utest
	@cd pkg/inngest_encryption && make utest
