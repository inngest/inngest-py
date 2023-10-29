from datetime import timedelta

from . import function_config


def test_serialization() -> None:
    data = function_config.FunctionConfig(
        batch_events=function_config.BatchConfig(
            max_size=10,
            timeout=timedelta(seconds=60),
        ),
        cancel=function_config.CancelConfig(
            event="foo",
            if_exp="foo",
            timeout=timedelta(seconds=60),
        ),
        id="foo",
        name="foo",
        steps={
            "foo": function_config.StepConfig(
                id="foo",
                name="foo",
                retries=function_config.RetriesConfig(attempts=1),
                runtime=function_config.Runtime(type="http", url="foo"),
            )
        },
        throttle=function_config.ThrottleConfig(
            key="foo",
            count=1,
            period=timedelta(seconds=60),
        ),
        triggers=[
            function_config.TriggerCron(cron="foo"),
            function_config.TriggerEvent(event="foo", expression="foo"),
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
