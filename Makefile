check-venv:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

format: check-venv
	@black inngest

format-check: check-venv
	@black --check inngest

install: check-venv
	@pip install '.[extra]' -c constraints.txt

precommit: format-check lint test type-check

lint: check-venv
	@pylint inngest

test: check-venv
	@pytest inngest

type-check: check-venv
	@mypy inngest
