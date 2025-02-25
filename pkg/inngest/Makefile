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
	@cd ../../tests/test_inngest && pytest -n 4 -v -x .

.PHONY: lint
lint: check-venv
	@ruff check .

release:
	@grep "version = \"$${VERSION}\"" pyproject.toml && git tag inngest@$${VERSION} && git push origin inngest@$${VERSION} || echo "pyproject.toml version does not match"

.PHONY: type-check
type-check: check-venv
	@mypy --config-file=../../mypy.ini .

.PHONY: utest
utest: check-venv
	@pytest -v inngest
