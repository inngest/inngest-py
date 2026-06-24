# Update dependencies

Area: Packaging
Change type: Maintenance

## Problem

Some dependencies are old.

## Solution

Update the dependencies listed below and make Python 3.11 the minimum supported Python version.

## Dependency updates

| Dependency | Current version | Target version | Location |
| --- | --- | --- | --- |
| Python | `>=3.10` | `>=3.11` | root and package `pyproject.toml` files, package classifiers, CI/test config |
| Django | `5.0` | `5.1.0` | `pyproject.toml` dev |
| Flask | `3.0.0` | `3.1.0` | `pyproject.toml` dev, `pkg/test_core/pyproject.toml` |
| boto3 | `1.35.47` | TBD | `pyproject.toml` dev |
| boto3-stubs[s3] | `1.35.46` | TBD | `pyproject.toml` dev |
| build | `1.0.3` | TBD | `pyproject.toml` dev |
| cryptography | `42.0.5` | TBD | `pyproject.toml` dev |
| django-types | `0.19.1` | TBD | `pyproject.toml` dev |
| fastapi | `0.110.0` | `0.115.0` | `pyproject.toml` dev, `pkg/test_core/pyproject.toml`, `constraint-dependencies` |
| httpx | `0.26.0` | `0.28.0` | `pkg/inngest/pyproject.toml`, `pkg/test_core/pyproject.toml`, `constraint-dependencies` |
| jcs | `0.2.1` | TBD | `pkg/inngest/pyproject.toml`, `constraint-dependencies` |
| moto[s3,server] | `5.0.18` | TBD | `pyproject.toml` dev |
| mypy | `1.10.0` | TBD | `pyproject.toml` dev |
| protobuf | `5.29.4` | `7.35.0` | `pkg/inngest/pyproject.toml` connect extra, `constraint-dependencies` |
| psutil | `6.0.0` | `7.2.0` | `pkg/inngest/pyproject.toml` connect extra, `constraint-dependencies` |
| pydantic | `2.11.0` | `2.13.0` | `pkg/inngest/pyproject.toml`, `constraint-dependencies` |
| pynacl | `1.5.0` | TBD | `pkg/inngest_encryption/pyproject.toml`, `pyproject.toml` dev, `constraint-dependencies` |
| pyright | `1.1.402` | TBD | `pyproject.toml` dev |
| pytest | `9.0.3` | TBD | `pyproject.toml` dev |
| pytest-django | `4.7.0` | TBD | `pyproject.toml` dev |
| pytest-timeout | `2.3.1` | TBD | `pyproject.toml` dev |
| pytest-xdist[psutil] | `3.3.1` | TBD | `pyproject.toml` dev |
| ruff | `0.9.5` | TBD | `pyproject.toml` dev |
| sentry-sdk | `2.1.1` | TBD | `pyproject.toml` dev |
| structlog | `25.2.0` | TBD | `pyproject.toml` dev |
| toml | `0.10.2` | TBD | `pyproject.toml` dev |
| tornado | `6.5` | TBD | `pyproject.toml` dev |
| types-protobuf | `5.29.1.20250315` | TBD | `pyproject.toml` dev |
| types-psutil | `7.0.0.20250401` | TBD | `pyproject.toml` dev |
| types-toml | `0.10.8.7` | TBD | `pyproject.toml` dev |
| types-tornado | `5.1.1` | TBD | `pyproject.toml` dev |
| typing-extensions | `4.13.0` | `4.15.0` | `pkg/inngest/pyproject.toml`, `constraint-dependencies` |
| uvicorn | `0.23.2` | TBD | `pyproject.toml` dev |
| websockets | `15.0.0` | `16.0` | `pkg/inngest/pyproject.toml` connect extra, `constraint-dependencies` |

## Implementation

Update the relevant `pyproject.toml` files and regenerate `uv.lock`.

Update package classifiers and CI/test configuration to remove Python 3.10.

If a runtime lower bound changes, update the matching `constraint-dependencies` entry.

## Tests

Run the normal unit, lint, and type-check targets on supported Python versions after updating dependencies.
