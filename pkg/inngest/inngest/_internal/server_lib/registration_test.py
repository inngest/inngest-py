import datetime

from .registration import (
    Batch,
    Cancel,
    Concurrency,
    Debounce,
    FunctionConfig,
    Priority,
    RateLimit,
    Retries,
    Runtime,
    Singleton,
    Step,
    Throttle,
    Timeouts,
    TriggerCron,
    TriggerEvent,
)


def test_serialization() -> None:
    data = FunctionConfig(
        batch_events=Batch(
            max_size=10,
            timeout=datetime.timedelta(seconds=60),
            key="foo",
            if_exp="bar",
        ),
        cancel=[
            Cancel(
                event="foo",
                if_exp="foo",
                timeout=datetime.timedelta(seconds=60),
            )
        ],
        concurrency=[
            Concurrency(
                key="foo",
                limit=1,
                scope="account",
            )
        ],
        debounce=Debounce(
            key="foo",
            period=datetime.timedelta(seconds=60),
            timeout=datetime.timedelta(minutes=2),
        ),
        id="foo",
        idempotency="event.data.foo",
        name="foo",
        priority=Priority(
            run="event.data.plan == 'enterprise' ? 180 : 0",
        ),
        steps={
            "foo": Step(
                id="foo",
                name="foo",
                retries=Retries(attempts=1),
                runtime=Runtime(type="http", url="foo"),
            )
        },
        rate_limit=RateLimit(
            key="foo",
            limit=1,
            period=datetime.timedelta(seconds=60),
        ),
        throttle=Throttle(
            key="foo",
            limit=1,
            period=datetime.timedelta(seconds=60),
        ),
        timeouts=Timeouts(
            start=datetime.timedelta(minutes=5),
            finish=datetime.timedelta(hours=1),
        ),
        singleton=Singleton(
            key="foo",
            mode="skip",
        ),
        triggers=[
            TriggerCron(cron="foo"),
            TriggerEvent(event="foo", expression="foo"),
        ],
    ).to_dict()
    if isinstance(data, Exception):
        raise data

    assert data == {
        "batchEvents": {
            "maxSize": 10,
            "timeout": "1m",
            "key": "foo",
            "if": "bar",
        },
        "cancel": [
            {
                "event": "foo",
                "if": "foo",
                "timeout": "1m",
            }
        ],
        "concurrency": [
            {
                "key": "foo",
                "limit": 1,
                "scope": "account",
            }
        ],
        "debounce": {
            "key": "foo",
            "period": "1m",
            "timeout": "2m",
        },
        "id": "foo",
        "idempotency": "event.data.foo",
        "name": "foo",
        "priority": {
            "run": "event.data.plan == 'enterprise' ? 180 : 0",
        },
        "rateLimit": {
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
            "limit": 1,
            "burst": 1,
            "period": "1m",
        },
        "timeouts": {
            "start": "5m",
            "finish": "1h",
        },
        "singleton": {
            "key": "foo",
            "mode": "skip",
        },
        "triggers": [
            {"cron": "foo"},
            {
                "event": "foo",
                "expression": "foo",
            },
        ],
    }
