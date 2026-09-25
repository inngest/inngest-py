"""
Focused checks for middleware isolation and execution-local session state.
Only outbound HTTP is mocked; real-server propagation and resolution are covered
in tests/test_inngest/test_function/cases/session_*.py.
"""

from __future__ import annotations

import asyncio
import json
import threading
import typing
import unittest

import httpx

import inngest

from . import (
    comm_lib,
    net,
    server_lib,
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
        run_id: str = "original",
    ) -> tuple[int, typing.Any]:
        event = inngest.Event(
            name="start", meta={"sessions": {"conversation": "chat-1"}}
        )
        body = {
            "ctx": {
                "run_id": run_id,
                "attempt": 0,
                "disable_immediate_execution": False,
                "stack": {"stack": []},
            },
            "event": event.to_dict(),
            "events": [event.to_dict()],
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
            response = await handler.post(req)
            encoded = response.body_bytes()
            assert isinstance(encoded, bytes)
            return response.status_code, json.loads(encoded)
        finally:
            if handler._thread_pool is not None:
                handler._thread_pool.shutdown()


class TestSessionPropagation(unittest.TestCase):
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
