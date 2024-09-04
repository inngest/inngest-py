.PHONY: build
build:
	@if [ -d "dist" ]; then rm -rf dist; fi
	@python -m build

check-venv:
	@if [ -z "$${CI}" ] && [ -z "$${VIRTUAL_ENV}" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

format: check-venv
	@ruff format --check .

format-check: check-venv
	@ruff format .

install: check-venv
	@pip install -e '.[extra]' -c constraints.txt

itest: check-venv
	@pytest -n 4 -v tests

pre-commit: format-check lint type-check utest

release:
	@grep  "version = \"$${VERSION}\"" pyproject.toml && git tag $${VERSION} && git push origin $${VERSION} || echo "pyproject.toml version does not match"

lint: check-venv
	@ruff check .

type-check: check-venv
	@mypy inngest tests
	@mypy examples/fast_api
	@mypy examples/flask
	@mypy examples/tornado

utest: check-venv
	@pytest -v inngest
