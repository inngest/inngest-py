set -e

# Ensure that virtual environment is activated.
if [ -z "$VIRTUAL_ENV" ]; then
    python -m venv .venv
    source .venv/bin/activate
fi

pip install .
