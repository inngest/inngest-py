export MYPYPATH=../inngest

.PHONY: build
build:
	@if [ -d "dist" ]; then rm -rf dist; fi
	@uv build

.PHONY: itest
itest:
	@cd ../.. && uv run pytest -n 4 -v tests/test_inngest_encryption

.PHONY: lint
lint:
	@uv run ruff check .

release:
	@grep "version = \"$${VERSION}\"" pyproject.toml && git tag inngest_encryption@$${VERSION} && git push origin inngest_encryption@$${VERSION} || echo "pyproject.toml version does not match"

.PHONY: type-check
type-check:
	@uv run mypy --config-file=../../mypy.ini .

.PHONY: utest
utest:
	@echo "inngest_encryption unit tests not implemented"
