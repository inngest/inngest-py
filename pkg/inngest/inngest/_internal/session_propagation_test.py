"""
Only the outbound HTTP transport is mocked. Incoming events represent metadata
already resolved by the server; these tests do not emulate server-side merging.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
import typing
import unittest

import fastapi
import httpx

import inngest
import inngest.fast_api

from . import (
    comm_lib,
    net,
    server_lib,
    sessions,
)


class SessionHarness:
    """
    Exercise SDK request handling with only the event API replaced by a mock.
    """

    def __init__(self) -> None:
        self.client = inngest.Inngest(
            app_id="sessions",
            is_production=False,
            api_base_url="http://sdk.test",
            event_api_base_url="http://sdk.test",
        )
        self.requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            assert request.url.path.startswith("/e/"), "Unexpected API request"
            self.requests.append(request)
            return httpx.Response(
                200, json={"ids": ["event-id"], "status": 200}
            )

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
        event: inngest.Event | None = None,
        events: list[inngest.Event] | None = None,
        run_id: str = "original",
        sync_dispatch: bool = False,
    ) -> tuple[int, typing.Any]:
        if event is None:
            event = (
                events[0]
                if events
                else inngest.Event(
                    name="start", meta={"sessions": {"conversation": "chat-1"}}
                )
            )
        body = {
            "ctx": {
                "run_id": run_id,
                "attempt": 0,
                "disable_immediate_execution": False,
                "stack": {"stack": []},
            },
            "event": event.to_dict(),
            "events": [
                e.to_dict() for e in (events if events is not None else [event])
            ],
            "steps": {},
            "use_api": False,
        }
        query = {"fnId": fn.id}
        req = comm_lib.CommRequest(
            body=json.dumps(body).encode(),
            headers={},
            is_connect=False,
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
            # Most cases use async dispatch, which runs sync handlers in workers.
            # A focused case below also exercises synchronous serving directly.
            response = (
                handler.post_sync(req)
                if sync_dispatch
                else await handler.post(req)
            )
            encoded = response.body_bytes()
            assert isinstance(encoded, bytes)
            return response.status_code, json.loads(encoded)
        finally:
            if handler._thread_pool is not None:
                handler._thread_pool.shutdown()


@dataclasses.dataclass
class BatchCase:
    name: str
    events: list[inngest.Event]
    expected_sessions: dict[str, str]


class TestSessionPropagation(unittest.TestCase):
    def test_batch_children_inherit_only_sessions_shared_by_every_event(
        self,
    ) -> None:
        """
        A batch spanning different conversations must not attribute all of its
        child work to one conversation. Only grouping shared by the entire batch
        is safe. Check both what the handler sees and what its child event
        actually sends.

        If we don't enforce this invariant, then event batching could lead to
        sessions bleeding into each other.
        """

        first = inngest.Event(
            name="start",
            meta={
                "sessions": {
                    "user": "alice",
                    "conversation": "chat-1",
                    "request": "first-only",
                }
            },
        )
        second = inngest.Event(
            name="start",
            meta={"sessions": {"user": "alice", "conversation": "chat-2"}},
        )
        cases: list[BatchCase] = [
            BatchCase(
                "shared user, different conversations",
                [first, second],
                {"user": "alice"},
            ),
            BatchCase(
                "batch order does not select a conversation",
                [second, first],
                {"user": "alice"},
            ),
            BatchCase(
                "one event has no sessions",
                [first, inngest.Event(name="start")],
                {},
            ),
        ]
        for mode, is_sync in [("async", False), ("sync", True)]:
            for case in cases:
                with self.subTest(mode=mode, case=case.name):
                    harness = SessionHarness()

                    def sync(ctx: inngest.ContextSync) -> dict[str, str]:
                        harness.client.send_sync(inngest.Event(name="child"))
                        return ctx.sessions

                    async def async_fn(ctx: inngest.Context) -> dict[str, str]:
                        await harness.client.send(inngest.Event(name="child"))
                        return ctx.sessions

                    fn = harness.client.create_function(
                        fn_id=mode, trigger=inngest.TriggerEvent(event="start")
                    )(sync if is_sync else async_fn)
                    status, seen_sessions = asyncio.run(
                        harness.request(fn, events=case.events)
                    )
                    description = f"{mode}: {case.name}"
                    assert status == 200, description
                    assert seen_sessions == case.expected_sessions, description
                    assert len(harness.requests) == 1, description
                    child = json.loads(harness.requests[0].content)[0]
                    assert (
                        child.get("meta", {}).get("propagated_sessions", {})
                        == case.expected_sessions
                    ), description

    def test_child_sends_distinguish_inheritance_from_explicit_removal(
        self,
    ) -> None:
        """
        Ensure child events inherit the parent's sessions and preserve explicit
        removal instructions for the server to apply. Treating empty overrides
        as null would silently break grouping; dropping an explicit null would
        keep an unwanted association.

        Verify the SDK sends inheritance and removal instructions distinctly.
        The server, rather than the SDK, applies the removal to the inherited
        layer.  Removing the conversation alone must leave the user session
        available to inherit; it must not become an instruction to remove all
        sessions.
        """

        cases: list[
            tuple[str, sessions.EventMeta | None, dict[str, str | None] | None]
        ] = [
            ("absent metadata", None, {}),
            ("empty metadata", {}, {}),
            ("empty overrides", {"sessions": {}}, {}),
            ("remove all sessions", {"sessions": None}, None),
            (
                "remove only conversation",
                {"sessions": {"conversation": None}},
                {"conversation": None},
            ),
        ]
        modes: list[tuple[str, bool]] = [("async", False), ("sync", True)]
        for mode, is_sync in modes:
            with self.subTest(mode=mode):
                events = [
                    inngest.Event(name=name, meta=meta)
                    for name, meta, _ in cases
                ]
                harness = SessionHarness()
                parent = inngest.Event(
                    name="start",
                    meta={
                        "sessions": {"conversation": "chat-1", "user": "alice"}
                    },
                )

                def sync(ctx: inngest.ContextSync) -> None:
                    ctx.step.send_event("children", events)

                async def async_fn(ctx: inngest.Context) -> None:
                    await ctx.step.send_event("children", events)

                fn = harness.client.create_function(
                    fn_id=mode, trigger=inngest.TriggerEvent(event="start")
                )(sync if is_sync else async_fn)
                status, _ = asyncio.run(harness.request(fn, event=parent))
                assert status == 206, mode
                assert len(harness.requests) == 1, mode
                sent = json.loads(harness.requests[0].content)
                assert len(sent) == len(cases), mode
                for event, (name, _, expected_overrides) in zip(sent, cases):
                    description = f"{mode}: {name}"
                    assert event["name"] == name, description
                    meta = event["meta"]
                    assert meta["propagated_sessions"] == {
                        "conversation": "chat-1",
                        "user": "alice",
                    }, description
                    # Omission and {} both allow inheritance. Whole-field and per-key
                    # nulls must survive stamping as distinct removal instructions.
                    assert meta.get("sessions", {}) == expected_overrides, (
                        description
                    )

    def test_send_middleware_change_isolation(self) -> None:
        """
        A handler uses step.send_event to send the same event object twice. Both
        outgoing events inherit its conversation, then send middleware changes
        the conversation on only the first event. The client must preserve that
        change when the step delegates the send to it.

        That change must not affect the second event, the handler's
        ctx.sessions, or the original event object. Otherwise, changing one
        child's session could unexpectedly assign other work to the wrong
        conversation.
        """

        for mode, is_sync in [("async", False), ("sync", True)]:
            with self.subTest(mode=mode):
                harness = SessionHarness()
                outgoing = inngest.Event(name="child")
                parent_sessions: dict[str, str] | None = None

                class Middleware(inngest.MiddlewareSync):
                    def before_send_events(
                        self, events: list[inngest.Event]
                    ) -> None:
                        meta = events[0].meta
                        assert meta is not None
                        meta["propagated_sessions"]["conversation"] = "changed"
                        assert parent_sessions == {"conversation": "chat-1"}

                def sync(ctx: inngest.ContextSync) -> None:
                    nonlocal parent_sessions
                    parent_sessions = ctx.sessions
                    ctx.step.send_event("children", [outgoing, outgoing])

                async def async_fn(ctx: inngest.Context) -> None:
                    nonlocal parent_sessions
                    parent_sessions = ctx.sessions
                    await ctx.step.send_event("children", [outgoing, outgoing])

                harness.client.add_middleware(Middleware)
                fn = harness.client.create_function(
                    fn_id="fn", trigger=inngest.TriggerEvent(event="start")
                )(sync if is_sync else async_fn)
                status, operations = asyncio.run(harness.request(fn))
                assert status == 206
                assert operations[0]["data"] == ["event-id"]
                assert len(harness.requests) == 1
                sent = json.loads(harness.requests[0].content)
                assert len(sent) == 2
                assert sent[0]["meta"]["propagated_sessions"] == {
                    "conversation": "changed"
                }
                assert sent[1]["meta"]["propagated_sessions"] == {
                    "conversation": "chat-1"
                }
                assert parent_sessions == {"conversation": "chat-1"}
                assert outgoing.meta is None

    def test_invoke_inherits_current_sessions_and_preserves_clear_override(
        self,
    ) -> None:
        """
        Invoked functions need the same inheritance and explicit opt-out behavior
        as child events; their metadata travels in an invoke operation instead.
        """

        cases: list[tuple[str, bool]] = [
            ("async", False),
            ("sync", True),
        ]
        for case, is_sync in cases:
            with self.subTest(case=case):
                harness = SessionHarness()

                @harness.client.create_function(
                    fn_id="child", trigger=inngest.TriggerEvent(event="child")
                )
                def child(ctx: inngest.ContextSync) -> None:
                    pass

                def sync(ctx: inngest.ContextSync) -> None:
                    ctx.sessions["user"] = "u1"
                    ctx.step.invoke(
                        "invoke", function=child, meta={"sessions": None}
                    )

                async def async_fn(ctx: inngest.Context) -> None:
                    ctx.sessions["user"] = "u1"
                    await ctx.step.invoke(
                        "invoke", function=child, meta={"sessions": None}
                    )

                fn = harness.client.create_function(
                    fn_id="fn", trigger=inngest.TriggerEvent(event="start")
                )(sync if is_sync else async_fn)
                status, operations = asyncio.run(harness.request(fn))
                assert status == 206, case
                invoke_operation = operations[0]
                assert invoke_operation["opts"]["function_id"] == child.id, case
                assert invoke_operation["opts"]["payload"]["meta"] == {
                    "sessions": None,
                    "propagated_sessions": {
                        "conversation": "chat-1",
                        "user": "u1",
                    },
                }, case

    def test_bare_client_send(self) -> None:
        """
        Direct client sends inside handlers must inherit the latest context
        sessions, including edits made after an earlier send.

        Internally we use ContextVar to infer the sessions.
        """

        cases: list[tuple[str, bool]] = [
            ("async", False),
            ("sync", True),
        ]
        for case, is_sync in cases:
            with self.subTest(case=case):
                harness = SessionHarness()

                def sync(ctx: inngest.ContextSync) -> None:
                    harness.client.send_sync(inngest.Event(name="before"))
                    ctx.sessions["conversation"] = "changed"
                    harness.client.send_sync(inngest.Event(name="after"))

                async def async_fn(ctx: inngest.Context) -> None:
                    await harness.client.send(inngest.Event(name="before"))
                    ctx.sessions["conversation"] = "changed"
                    await harness.client.send(inngest.Event(name="after"))

                fn = harness.client.create_function(
                    fn_id="fn", trigger=inngest.TriggerEvent(event="start")
                )(sync if is_sync else async_fn)
                status, _ = asyncio.run(harness.request(fn))
                assert status == 200, case
                sent = [
                    json.loads(request.content)[0]
                    for request in harness.requests
                ]
                assert [
                    event["meta"]["propagated_sessions"] for event in sent
                ] == [
                    {"conversation": "chat-1"},
                    {"conversation": "changed"},
                ], case

    def test_concurrent_runs_keep_sessions_separate(self) -> None:
        """
        Overlapping runs must not attach one conversation's child events to
        another conversation, including when sync handlers run in worker
        threads. This is critical because many runs can share the same client.
        """

        cases: list[tuple[str, bool]] = [
            ("async", False),
            ("sync", True),
        ]
        for case, is_sync in cases:
            with self.subTest(case=case):
                harness = SessionHarness()
                thread_barrier = threading.Barrier(2, timeout=5)

                async def check() -> None:
                    both_running = asyncio.Event()
                    arrivals = 0

                    def sync(ctx: inngest.ContextSync) -> None:
                        ctx.sessions["conversation"] = ctx.run_id
                        thread_barrier.wait()
                        harness.client.send_sync(inngest.Event(name=ctx.run_id))

                    async def async_fn(ctx: inngest.Context) -> None:
                        nonlocal arrivals
                        ctx.sessions["conversation"] = ctx.run_id
                        arrivals += 1
                        if arrivals == 2:
                            both_running.set()
                        await asyncio.wait_for(both_running.wait(), timeout=5)
                        await harness.client.send(
                            inngest.Event(name=ctx.run_id)
                        )

                    fn = harness.client.create_function(
                        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
                    )(sync if is_sync else async_fn)
                    # Async dispatch puts sync handlers in workers, allowing their runs to overlap.
                    results = await asyncio.gather(
                        *[
                            harness.request(fn, run_id=run_id)
                            for run_id in ("first", "second")
                        ]
                    )
                    assert all(status == 200 for status, _ in results), case

                asyncio.run(check())
                sent = [
                    json.loads(request.content)[0]
                    for request in harness.requests
                ]
                assert {event["name"] for event in sent} == {
                    "first",
                    "second",
                }, case
                for event in sent:
                    assert event["meta"]["propagated_sessions"] == {
                        "conversation": event["name"]
                    }, case

    def test_finished_runs_do_not_leak_sessions_into_response_or_later_sends(
        self,
    ) -> None:
        """
        After a run finishes or fails, later sends must not inherit its
        sessions.
        """

        cases: list[tuple[str, bool, bool]] = [
            ("async success", False, False),
            ("async failure", False, True),
            ("sync success", True, False),
            ("sync failure", True, True),
        ]
        for case, is_sync, should_fail in cases:
            with self.subTest(case=case):
                harness = SessionHarness()

                class Middleware(inngest.MiddlewareSync):
                    def before_execution(self) -> None:
                        self.client.send_sync(
                            inngest.Event(name="before-execution")
                        )

                    def after_execution(self) -> None:
                        self.client.send_sync(
                            inngest.Event(name="after-execution")
                        )

                    def transform_output(
                        self, result: inngest.TransformOutputResult
                    ) -> None:
                        self.client.send_sync(
                            inngest.Event(name="transform-output")
                        )

                    def before_response(self) -> None:
                        # Runs on the execution thread, also checking sync worker cleanup.
                        self.client.send_sync(
                            inngest.Event(name="before-response")
                        )

                def sync(ctx: inngest.ContextSync) -> None:
                    ctx.sessions["conversation"] = "changed"
                    if should_fail:
                        raise ValueError("intentional failure")

                async def async_fn(ctx: inngest.Context) -> None:
                    ctx.sessions["conversation"] = "changed"
                    if should_fail:
                        raise ValueError("intentional failure")

                fn = harness.client.create_function(
                    fn_id="fn",
                    trigger=inngest.TriggerEvent(event="start"),
                    middleware=[Middleware],
                )(sync if is_sync else async_fn)
                status, _ = asyncio.run(harness.request(fn))
                assert status == (500 if should_fail else 200), case
                harness.client.send_sync(inngest.Event(name="outside-run"))
                sent = [
                    json.loads(request.content)[0]
                    for request in harness.requests
                ]
                inherited = {
                    event["name"]: event.get("meta", {}).get(
                        "propagated_sessions", {}
                    )
                    for event in sent
                }
                expected = {
                    "before-execution": {"conversation": "chat-1"},
                    "transform-output": {},
                    "before-response": {},
                    "outside-run": {},
                }
                if not should_fail:
                    expected["after-execution"] = {"conversation": "changed"}
                assert inherited == expected, case

    def test_synchronous_serving_initializes_and_propagates_sessions(
        self,
    ) -> None:
        """
        Synchronous adapters use post_sync, which constructs its own execution
        context. Verify that path supplies sessions to the handler and child
        sends.
        """

        harness = SessionHarness()

        @harness.client.create_function(
            fn_id="fn", trigger=inngest.TriggerEvent(event="start")
        )
        def parent(ctx: inngest.ContextSync) -> dict[str, str]:
            harness.client.send_sync(inngest.Event(name="child"))
            return ctx.sessions

        status, seen = asyncio.run(harness.request(parent, sync_dispatch=True))
        assert status == 200
        assert seen == {"conversation": "chat-1"}
        assert len(harness.requests) == 1
        child = json.loads(harness.requests[0].content)[0]
        assert child["meta"]["propagated_sessions"] == {
            "conversation": "chat-1"
        }

    def test_fastapi_endpoint_propagates_sessions_into_child_events(
        self,
    ) -> None:
        """
        Register a handler through the public adapter and execute its serving
        endpoint in process. This covers framework wiring and request/response
        conversion without requiring a Dev Server or pretending to resolve sessions.
        """
        harness = SessionHarness()
        app = fastapi.FastAPI()

        @harness.client.create_function(
            fn_id="parent", trigger=inngest.TriggerEvent(event="start")
        )
        async def parent(ctx: inngest.Context) -> None:
            await ctx.step.send_event("child", inngest.Event(name="child"))

        # Pin the route so ambient INNGEST_SERVE_PATH settings cannot change it.
        inngest.fast_api.serve(
            app, harness.client, [parent], serve_path="/api/inngest"
        )
        incoming = inngest.Event(
            name="start", meta={"sessions": {"conversation": "chat-1"}}
        )

        async def check() -> None:
            async with httpx.AsyncClient(
                # httpx 0.26's ASGI callable types are narrower than Starlette's.
                transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
                base_url="http://app.test",
            ) as browser:
                inspection = await browser.get("/api/inngest")
                assert inspection.status_code == 200
                assert inspection.json()["function_count"] == 1
                response = await browser.post(
                    "/api/inngest",
                    params={"fnId": parent.id},
                    json={
                        "ctx": {
                            "run_id": "parent-run",
                            "attempt": 0,
                            "disable_immediate_execution": False,
                            "stack": {"stack": []},
                        },
                        "event": incoming.to_dict(),
                        "events": [incoming.to_dict()],
                        "steps": {},
                        "use_api": False,
                    },
                )
                assert response.status_code == 206
                assert response.json()[0]["data"] == ["event-id"]

        asyncio.run(check())
        assert len(harness.requests) == 1
        child = json.loads(harness.requests[0].content)[0]
        assert child["name"] == "child"
        assert child["meta"]["propagated_sessions"] == {
            "conversation": "chat-1"
        }
