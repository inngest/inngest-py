check-venv:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

dev: check-venv
	@export INNGEST_DEV=1 FLASK_DEBUG=true && ./scripts/start.sh

install: check-venv
	@pip install .

prod: check-venv
	@sh ./scripts/start.sh
