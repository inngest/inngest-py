format:
	black inngest

format-check:
	black --check inngest

precommit: format-check lint type-check

lint:
	pylint inngest

type-check:
	mypy inngest
