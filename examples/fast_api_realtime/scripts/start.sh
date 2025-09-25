set -e

export PYTHONPATH=${PYTHONPATH}:../..

# Load env vars from .env file in repo root.
if [ -f ../../.env ]; then
    echo "Loading env vars from ../../.env"
    ENV_VARS=$(cat ../../.env | grep -v ^#)
    if [ -n "${ENV_VARS}" ]; then
        export $(echo ${ENV_VARS} | xargs)
    fi
fi

uv run --project ../.. uvicorn app:app --reload
