check-venv:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "virtual environment is not activated"; \
		exit 1; \
	fi

dev: check-venv
	@export INNGEST_DEV=1 && ./scripts/start.sh