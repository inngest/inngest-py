export MYPYPATH=../inngest

.PHONY: build
build:
	@if [ -d "dist" ]; then rm -rf dist; fi
	@uv build --out-dir dist

.PHONY: itest
itest:
	@cd ../.. && uv run pytest -n 4 -sv tests/test_inngest_langchain

.PHONY: lint
lint:
	@uv run ruff check .

release:
	@grep "version = \"$${VERSION}\"" pyproject.toml && git tag inngest_langchain@$${VERSION} && git push origin inngest_langchain@$${VERSION} || echo "pyproject.toml version does not match"

.PHONY: type-check
type-check:
	@uv run mypy --config-file=../../mypy.ini .

.PHONY: utest
utest:
	@uv run pytest -v inngest_langchain
