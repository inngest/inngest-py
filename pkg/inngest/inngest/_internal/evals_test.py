from __future__ import annotations

import asyncio
import json
import threading
import typing

import httpx
import pydantic
import pytest

import inngest

from . import (
    comm_lib,
    net,
    run_context,
    server_lib,
    sessions,
)


class Harness:
    def __init__(self) -> None:
        self.client = inngest.Inngest(
            app_id="evals",
            is_production=False,
            api_base_url="http://sdk.test",
            event_api_base_url="http://sdk.test",
        )
        self.requests: list[httpx.Request] = []
        self.status = 204

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path.startswith("/e/"):
                return httpx.Response(
                    200, json={"ids": ["event-id"], "status": 200}
                )
            return httpx.Response(self.status)

        transport = httpx.MockTransport(handle)
        self.client._http_client._http_client_sync = httpx.Client(
            transport=transport
        )
        self.client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
            transport=transport
        ).initialize()

    async def request(
        self,
        fn: inngest.Function[typing.Any],
        *,
        memos: dict[str, object] | None = None,
        event: inngest.Event | None = None,
        events: list[inngest.Event] | None = None,
        run_id: str = "original",
        attempt: int = 0,
        target: str | None = None,
        is_connect: bool = False,
    ) -> tuple[int, typing.Any]:
        event = event or inngest.Event(
            name="start", meta={"sessions": {"conversation": "chat-1"}}
        )
        body = {
            "ctx": {
                "run_id": run_id,
                "attempt": attempt,
                "disable_immediate_execution": False,
                "stack": {"stack": []},
            },
            "event": event.to_dict(),
            "events": [
                e.to_dict() for e in (events if events is not None else [event])
            ],
            "steps": memos or {},
            "use_api": False,
        }
        query = {"fnId": fn.id}
        if target is not None:
            query["stepId"] = target
        req = comm_lib.CommRequest(
            body=json.dumps(body).encode(),
            headers={},
            is_connect=is_connect,
            public_path=None,
            query_params=query,
            raw_request=None,
            request_url="",
            serve_origin=None,
            serve_path=None,
        )
        handler = comm_lib.CommHandler(
            client=self.client,
            enable_unauthed_sync=None,
            framework=server_lib.Framework.FAST_API,
            functions=[fn],
            streaming=None,
        )
        try:
            response = (
                await handler.post(req)
                if fn.is_handler_async or is_connect
                else handler.post_sync(req)
            )
            encoded = response.body_bytes()
            assert isinstance(encoded, bytes)
            assert run_context.current_run.get() is None
            return response.status_code, json.loads(encoded)
        finally:
            if handler._thread_pool is not None:
                handler._thread_pool.shutdown()


@pytest.mark.parametrize("is_sync", [False, True])
@pytest.mark.parametrize("with_sessions", [False, True])
def test_send_payload_with_private_lock(
    is_sync: bool, with_sessions: bool
) -> None:
    class Payload(pydantic.BaseModel):
        value: str = "serializable"
        _lock: object = pydantic.PrivateAttr(default_factory=threading.Lock)

    class Event(inngest.Event):
        _lock: object = pydantic.PrivateAttr(default_factory=threading.Lock)

    event = Event(
        name="child",
        data={"nested": {"payload": Payload()}},
        meta={"sessions": {"conversation": "chat-1"}}
        if with_sessions
        else None,
    )
    harness = Harness()
    ids = (
        harness.client.send_sync(event)
        if is_sync
        else asyncio.run(harness.client.send(event))
    )
    assert ids == ["event-id"]
    sent = json.loads(harness.requests[0].content)[0]
    assert sent["data"] == {"nested": {"payload": {"value": "serializable"}}}
    assert sent.get("meta") == event.meta


@pytest.mark.parametrize("is_sync", [False, True])
def test_send_middleware_metadata_is_independent(is_sync: bool) -> None:
    class Middleware(inngest.MiddlewareSync):
        def before_send_events(self, events: list[inngest.Event]) -> None:
            meta = events[0].meta
            assert meta is not None
            manual = meta["sessions"]
            assert manual is not None
            manual["conversation"] = "changed"
            meta["propagated_sessions"]["user"] = "changed"

    harness = Harness()
    harness.client.middleware.append(Middleware)
    event = inngest.Event(
        name="child",
        meta={
            "sessions": {"conversation": "original"},
            "propagated_sessions": {"user": "original"},
        },
    )
    if is_sync:
        harness.client.send_sync([event, event])
    else:
        asyncio.run(harness.client.send([event, event]))
    sent = json.loads(harness.requests[0].content)
    assert sent[0]["meta"] == {
        "sessions": {"conversation": "changed"},
        "propagated_sessions": {"user": "changed"},
    }
    assert (
        sent[1]["meta"]
        == event.meta
        == {
            "sessions": {"conversation": "original"},
            "propagated_sessions": {"user": "original"},
        }
    )


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"exclude": {"meta"}}, None),
        ({"include": {"name"}}, None),
        (
            {"exclude": {"meta": {"sessions": {"secret"}}}},
            {
                "sessions": {"visible": "1"},
                "propagated_sessions": {"secret": "inherited", "visible": "2"},
            },
        ),
        (
            {"include": {"meta": {"sessions": {"visible"}}}},
            {"sessions": {"visible": "1"}},
        ),
        (
            {"exclude": {"meta": {"propagated_sessions": {"secret"}}}},
            {
                "sessions": {"secret": "manual", "visible": "1"},
                "propagated_sessions": {"visible": "2"},
            },
        ),
    ],
)
def test_metadata_serialization_respects_filters(
    json_mode: bool,
    filters: dict[str, typing.Any],
    expected: dict[str, object] | None,
) -> None:
    event = inngest.Event(
        name="child",
        meta={
            "sessions": {"secret": "manual", "visible": 1},
            "propagated_sessions": {"secret": "inherited", "visible": 2},
        },
    )
    result = (
        json.loads(event.model_dump_json(**filters))
        if json_mode
        else event.model_dump(**filters)
    )
    if expected is None:
        assert "meta" not in result
    else:
        assert result["meta"] == expected


@pytest.mark.parametrize("is_sync", [False, True])
def test_sessions_send_and_invoke(is_sync: bool) -> None:
    harness = Harness()
    outgoing = inngest.Event(
        name="child", meta={"sessions": {"conversation": None}}
    )

    def sync(ctx: inngest.ContextSync) -> None:
        assert ctx.sessions == {"conversation": "chat-1"}
        ctx.sessions["user"] = "u1"
        ctx.step.send_event("send", outgoing)
        ctx.step.invoke_by_id(
            "invoke", function_id="child", meta={"sessions": None}
        )

    async def async_fn(ctx: inngest.Context) -> None:
        assert ctx.sessions == {"conversation": "chat-1"}
        ctx.sessions["user"] = "u1"
        await ctx.step.send_event("send", outgoing)
        await ctx.step.invoke_by_id(
            "invoke", function_id="child", meta={"sessions": None}
        )

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(sync if is_sync else async_fn)

    async def check() -> None:
        _, ops = await harness.request(fn)
        sent = json.loads(harness.requests[0].content)[0]
        assert sent["meta"] == {
            "sessions": {"conversation": None},
            "propagated_sessions": {"conversation": "chat-1", "user": "u1"},
        }
        _, ops = await harness.request(
            fn, memos={ops[0]["id"]: {"data": ["event-id"]}}
        )
        assert ops[0]["opts"]["payload"]["meta"] == {
            "sessions": None,
            "propagated_sessions": {"conversation": "chat-1", "user": "u1"},
        }
        assert outgoing.meta == {"sessions": {"conversation": None}}

    asyncio.run(check())


def test_metadata_tombstones_and_batch_intersection() -> None:
    assert "meta" not in inngest.Event(name="e").model_dump()
    assert (
        "meta"
        not in inngest.Event(name="e", meta={"sessions": {}}).model_dump()
    )
    assert inngest.Event(name="e", meta={"sessions": None}).model_dump()[
        "meta"
    ] == {"sessions": None}
    a = inngest.Event(
        name="e", meta={"sessions": {"shared": 1, "other": "a", "missing": "x"}}
    )
    b = inngest.Event(
        name="e", meta={"sessions": {"shared": "1", "other": "b"}}
    )
    assert sessions.reduce_sessions([a, b]) == {"shared": "1"}
    assert sessions.reduce_sessions([a, inngest.Event(name="e")]) == {}
    assert a.meta == {"sessions": {"shared": "1", "other": "a", "missing": "x"}}
    with pytest.raises(ValueError):
        inngest.Event.model_validate(
            {"name": "e", "meta": {"sessions": {"boolean": True}}}
        )
    with pytest.raises(ValueError):
        inngest.Event.model_validate(
            {"name": "e", "meta": {"propagated_sessions": {"cut": None}}}
        )


@pytest.mark.parametrize(
    "value,expected",
    [
        (1.0, "1"),
        (-0.0, "0"),
        (1e21, "1e+21"),
        (1e-7, "1e-7"),
        (1e-6, "0.000001"),
    ],
)
def test_numeric_sessions_match_javascript(value: float, expected: str) -> None:
    assert inngest.Event(name="e", meta={"sessions": {"id": value}}).meta == {
        "sessions": {"id": expected}
    }


def test_session_cap_and_unicode_ordering() -> None:
    layer: dict[str, str | int | float | None] = {
        key: key for key in ["\U00010000", "\ue000", "a", "b", "c", "d"]
    }
    event = inngest.Event(name="e", meta={"sessions": layer})
    assert list(sessions.reduce_sessions([event])) == [
        "a",
        "b",
        "c",
        "d",
        "\ue000",
    ]
