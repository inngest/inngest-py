export PYTHONPATH=${PYTHONPATH}:../..

ENV_VARS=$(cat ../../.env | grep -v ^#)
if [ -n "${ENV_VARS}" ]; then
    export $(echo ${ENV_VARS} | xargs)
fi

echo ${PYTHONPATH}
python ./app.py
