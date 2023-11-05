import datetime

from . import function_config


def test_serialization() -> None:
    data = function_config.FunctionConfig(
        batch_events=function_config.Batch(
            max_size=10,
            timeout=datetime.timedelta(seconds=60),
        ),
        cancel=[
            function_config.Cancel(
                event="foo",
                if_exp="foo",
                timeout=datetime.timedelta(seconds=60),
            )
        ],
        debounce=function_config.Debounce(
            key="foo",
            period=datetime.timedelta(seconds=60),
        ),
        id="foo",
        name="foo",
        steps={
            "foo": function_config.Step(
                id="foo",
                name="foo",
                retries=function_config.Retries(attempts=1),
                runtime=function_config.Runtime(type="http", url="foo"),
            )
        },
        rate_limit=function_config.RateLimit(
            key="foo",
            limit=1,
            period=datetime.timedelta(seconds=60),
        ),
        throttle=function_config.Throttle(
            key="foo",
            count=1,
            period=datetime.timedelta(seconds=60),
        ),
        triggers=[
            function_config.TriggerCron(cron="foo"),
            function_config.TriggerEvent(event="foo", expression="foo"),
        ],
    ).to_dict()
    if isinstance(data, Exception):
        raise data

    assert data == {
        "batch_events": {
            "max_size": 10,
            "timeout": "1m",
        },
        "cancel": [
            {
                "event": "foo",
                "if_exp": "foo",
                "timeout": "1m",
            }
        ],
        "debounce": {
            "key": "foo",
            "period": "1m",
        },
        "id": "foo",
        "name": "foo",
        "rate_limit": {
            "key": "foo",
            "limit": 1,
            "period": "1m",
        },
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
