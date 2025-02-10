export MYPYPATH=../pkg/inngest:../pkg/inngest_encryption:../pkg/test_core

.PHONY: check-venv
check-venv:
	@if [ -z "$${CI}" ] && [ -z "$${VIRTUAL_ENV}" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

.PHONY: lint
lint: check-venv
	@ruff check .

.PHONY: type-check
type-check: check-venv
	@mypy --config-file=../mypy.ini .
