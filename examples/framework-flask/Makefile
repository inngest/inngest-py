.EXPORT_ALL_VARIABLES:
PYTHONPATH=$${PYTHONPATH}:../..

dev:
	@export $(shell cat ../../.env | grep -v ^# | xargs) && python ./app.py
