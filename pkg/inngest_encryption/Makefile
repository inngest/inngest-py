export MYPYPATH=../inngest

.PHONY: build
build:
	@if [ -d "dist" ]; then rm -rf dist; fi
	@python -m build

.PHONY: check-venv
check-venv:
	@if [ -z "$${CI}" ] && [ -z "$${VIRTUAL_ENV}" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

.PHONY: itest
itest: check-venv
	@cd ../../tests/test_inngest_encryption && pytest -n 4 -v .

.PHONY: lint
lint: check-venv
	@ruff check .

release:
	@grep "version = \"$${VERSION}\"" pyproject.toml && git tag inngest_encryption@$${VERSION} && git push origin inngest_encryption@$${VERSION} || echo "pyproject.toml version does not match"

.PHONY: type-check
type-check: check-venv
	@mypy --config-file=../../mypy.ini .

.PHONY: utest
utest: check-venv
	@echo "inngest_encryption unit tests not implemented"
