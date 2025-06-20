set -e

export PYTHONPATH=${PYTHONPATH}:../../..

# Load env vars from .env file in repo root.
ENV_VARS=$(cat ../../../.env | grep -v ^#)
if [ -n "${ENV_VARS}" ]; then
    export $(echo ${ENV_VARS} | xargs)
fi

uvicorn app:app --reload 