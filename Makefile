check-venv:
	@if [ -z "$${CI}" ] && [ -z "$${VIRTUAL_ENV}" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

format: check-venv
	@ruff format .

format-check: check-venv
	@ruff format --check .

install: check-venv
	@pip install -e '.[extra]' -c constraints.txt
	@pip install -e ./pkg/inngest
	@pip install -e ./pkg/inngest_encryption
	@pip install -e ./pkg/inngest_remote_state
	@pip install -e ./pkg/test_core

itest: check-venv
	@cd pkg/inngest && make itest
	@cd pkg/inngest_encryption && make itest
	@cd pkg/inngest_remote_state && make itest

pre-commit: format-check lint type-check utest

lint: check-venv
	@cd examples && make lint
	@cd pkg/inngest && make lint
	@cd pkg/inngest_encryption && make lint
	@cd pkg/inngest_remote_state && make lint
	@cd pkg/test_core && make lint

type-check: check-venv
	@cd examples && make type-check
	@cd pkg/inngest && make type-check
	@cd pkg/inngest_encryption && make type-check
	@cd pkg/inngest_remote_state && make type-check
	@cd pkg/test_core && make type-check

utest: check-venv
	@cd pkg/inngest && make utest
	@cd pkg/inngest_encryption && make utest
	@cd pkg/inngest_remote_state && make utest
