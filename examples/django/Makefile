check-venv:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

dev: check-venv
	./scripts/start.sh

install: check-venv
	@pip install .

prod: check-venv
	./scripts/start.sh
