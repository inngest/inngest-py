set -e

export PYTHONPATH=${PYTHONPATH}:../..

# Load env vars from .env file in repo root.
ENV_VARS=$(cat ../../.env | grep -v ^#)
if [ -n "${ENV_VARS}" ]; then
    export $(echo ${ENV_VARS} | xargs)
fi

# Ensure that virtual environment is activated.
if [ -z "$VIRTUAL_ENV" ]; then
    python -m venv .venv
    source .venv/bin/activate
fi

python ./app.py
