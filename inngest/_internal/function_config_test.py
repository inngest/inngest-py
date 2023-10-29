import json
from datetime import timedelta

from .function_config import (
    BatchConfig,
    CancelConfig,
    FunctionConfig,
    RetriesConfig,
    Runtime,
    StepConfig,
    ThrottleConfig,
    TriggerCron,
    TriggerEvent,
)


def test_serialization() -> None:
    data = FunctionConfig(
        batch_events=BatchConfig(
            max_size=10,
            timeout=timedelta(seconds=60),
        ),
        cancel=CancelConfig(
            event="foo",
            if_exp="foo",
            timeout=timedelta(seconds=60),
        ),
        id="foo",
        name="foo",
        steps={
            "foo": StepConfig(
                id="foo",
                name="foo",
                retries=RetriesConfig(attempts=1),
                runtime=Runtime(type="http", url="foo"),
            )
        },
        throttle=ThrottleConfig(
            key="foo",
            count=1,
            period=timedelta(seconds=60),
        ),
        triggers=[
            TriggerCron(cron="foo"),
            TriggerEvent(event="foo", expression="foo"),
        ],
    ).to_dict()

    assert data == {
        "batch_events": {
            "max_size": 10,
            "timeout": "1m",
        },
        "cancel": {
            "event": "foo",
            "if_exp": "foo",
            "timeout": "1m",
        },
        "id": "foo",
        "name": "foo",
        "steps": {
            "foo": {
                "id": "foo",
                "name": "foo",
                "retries": {"attempts": 1},
                "runtime": {
                    "type": "http",
                    "url": "foo",
                },
            }
        },
        "throttle": {
            "key": "foo",
            "count": 1,
            "period": "1m",
        },
        "triggers": [
            {"cron": "foo"},
            {
                "event": "foo",
                "expression": "foo",
            },
        ],
    }
