.PHONY: build
build:
	@if [ -d "dist" ]; then rm -rf dist; fi
	@uv build --out-dir dist

.PHONY: itest
itest:
	@cd ../.. && uv run pytest -n 4 -v tests/test_inngest

.PHONY: lint
lint:
	@uv run ruff check .

.PHONY: proto
proto:
	@uv run protoc --proto_path=./inngest/connect/_internal/ --python_out=./inngest/connect/_internal/ ./inngest/connect/_internal/connect.proto --pyi_out=./inngest/connect/_internal/

release:
	@grep "version = \"$${VERSION}\"" pyproject.toml && git tag inngest@$${VERSION} && git push origin inngest@$${VERSION} || echo "pyproject.toml version does not match"

.PHONY: type-check
type-check:
	@uv run mypy --config-file=../../mypy.ini .

.PHONY: utest
utest:
	@uv run --extra connect pytest -v inngest
