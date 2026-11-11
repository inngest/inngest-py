import datetime
import time
from collections.abc import Iterator
from zoneinfo import ZoneInfo

import fastapi
import fastapi.testclient
import inngest
import inngest.fast_api
import pytest


@pytest.fixture(params=["UTC", "America/New_York", "Australia/Sydney"])
def local_timezone(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    if not hasattr(time, "tzset"):
        pytest.skip("Changing the process timezone requires tzset")
    with monkeypatch.context() as environment:
        environment.setenv("TZ", request.param)
        time.tzset()
        try:
            yield request.param
        finally:
            environment.undo()
            time.tzset()


@pytest.mark.parametrize("is_sync", [False, True])
@pytest.mark.parametrize(
    "duration_type", ["timedelta", "milliseconds", "absolute"]
)
@pytest.mark.parametrize("cross_dst", [False, True])
def test_sleep_duration(
    local_timezone: str,
    is_sync: bool,
    duration_type: str,
    cross_dst: bool,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    duration = datetime.timedelta(days=2)
    if cross_dst:
        zone = ZoneInfo(local_timezone)
        # Cross the next offset change without replacing the real clock.
        duration = next(
            (
                datetime.timedelta(days=days)
                for days in range(1, 367)
                if (now + datetime.timedelta(days=days))
                .astimezone(zone)
                .utcoffset()
                != now.astimezone(zone).utcoffset()
            ),
            datetime.timedelta(days=150),
        )
    sleep_duration: int | datetime.timedelta = (
        int(duration.total_seconds() * 1000)
        if duration_type == "milliseconds"
        else duration
    )
    client = inngest.Inngest(app_id="sleep-duration", is_production=False)

    @client.create_function(
        fn_id="sync", trigger=inngest.TriggerEvent(event="test/sleep")
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        if duration_type == "absolute":
            ctx.step.sleep_until("delay", now + duration)
        else:
            ctx.step.sleep("delay", sleep_duration)

    @client.create_function(
        fn_id="async", trigger=inngest.TriggerEvent(event="test/sleep")
    )
    async def fn_async(ctx: inngest.Context) -> None:
        if duration_type == "absolute":
            await ctx.step.sleep_until("delay", now + duration)
        else:
            await ctx.step.sleep("delay", sleep_duration)

    app = fastapi.FastAPI()
    inngest.fast_api.serve(
        app,
        client,
        [fn_sync] if is_sync else [fn_async],
        streaming=inngest.Streaming.DISABLE,
    )
    event: dict[str, object] = {"name": "test/sleep", "data": {}}
    with fastapi.testclient.TestClient(app) as transport:
        before = datetime.datetime.now(datetime.timezone.utc)
        response = transport.post(
            "/api/inngest",
            params={
                "fnId": "sleep-duration-sync"
                if is_sync
                else "sleep-duration-async",
                "stepId": "step",
            },
            json={
                "ctx": {
                    "attempt": 0,
                    "disable_immediate_execution": False,
                    "run_id": "sleep-duration",
                    "stack": {},
                },
                "event": event,
                "events": [event],
                "steps": {},
                "use_api": False,
            },
        )
        after = datetime.datetime.now(datetime.timezone.utc)

    assert response.status_code == 206
    operations = response.json()
    assert len(operations) == 1
    assert operations[0]["op"] == "Sleep"
    target = datetime.datetime.fromisoformat(
        operations[0]["name"].replace("Z", "+00:00")
    )
    if duration_type == "absolute":
        before = after = now
    assert before + duration - datetime.timedelta(milliseconds=1) <= target
    assert target <= after + duration
