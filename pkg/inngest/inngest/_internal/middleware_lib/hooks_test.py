"""
Middleware hook guarantees, exercised in-process through CommHandler.post.

before_response must run for every middleware, even on cancellation or when
another middleware's transform_output or before_response raises.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import json
import logging
import typing
import unittest

import httpx

import inngest

from .. import client_lib, comm_lib, errors, net, server_lib, transforms
from .manager import MiddlewareManager
from .middleware import UninitializedMiddleware


class _Harness:
    def __init__(self) -> None:
        self.log_records: list[str] = []
        self.response_headers: dict[str, str] = {}

        class _Handler(logging.Handler):
            def emit(_self, record: logging.LogRecord) -> None:
                self.log_records.append(record.getMessage())

        logger = logging.getLogger(f"hooks_test.{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.addHandler(_Handler())

        self.client = inngest.Inngest(
            app_id="hooks",
            is_production=False,
            api_base_url="http://sdk.test",
            event_api_base_url="http://sdk.test",
            logger=logger,
        )

        def handle(request: httpx.Request) -> httpx.Response:
            assert request.url.path.startswith("/e/"), "Unexpected API request"
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
        steps: dict[str, object] | None = None,
        target: str | None = None,
        handler: comm_lib.CommHandler | None = None,
    ) -> tuple[int, typing.Any]:
        event = inngest.Event(name="start")
        body = {
            "ctx": {
                "run_id": "run",
                "attempt": 0,
                "disable_immediate_execution": False,
                "stack": {"stack": []},
            },
            "event": event.to_dict(),
            "events": [event.to_dict()],
            "steps": steps or {},
            "use_api": False,
        }
        query = {"fnId": fn.id}
        if target is not None:
            query["stepId"] = transforms.hash_step_id(target)
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
        owns_handler = handler is None
        if handler is None:
            handler = self.create_handler(fn)
        try:
            response = await handler.post(req)
            self.response_headers = response.headers
            encoded = response.body_bytes()
            assert isinstance(encoded, bytes)
            return response.status_code, json.loads(encoded)
        finally:
            if owns_handler and handler._thread_pool is not None:
                handler._thread_pool.shutdown()

    def create_handler(
        self, fn: inngest.Function[typing.Any]
    ) -> comm_lib.CommHandler:
        return comm_lib.CommHandler(
            client=self.client,
            enable_unauthed_sync=None,
            framework=server_lib.Framework.FAST_API,
            functions=[fn],
            streaming=None,
        )


def _create_middleware(
    messages: list[str],
    *,
    is_sync: bool,
    raise_in: dict[str, str],
) -> tuple[UninitializedMiddleware, UninitializedMiddleware]:
    """
    Create middleware "A" and "B". raise_in maps a middleware name to the hook
    it raises in.
    """

    def factory(name: str) -> UninitializedMiddleware:
        def record(hook: str) -> None:
            messages.append(f"{name}.{hook}")
            if raise_in.get(name) == hook:
                raise Exception(f"{name}.{hook} failed")

        if is_sync:

            class _Sync(inngest.MiddlewareSync):
                def transform_output(
                    self, result: inngest.TransformOutputResult
                ) -> None:
                    record("transform_output")

                def before_response(self) -> None:
                    record("before_response")

            return _Sync

        class _Async(inngest.Middleware):
            async def transform_output(
                self, result: inngest.TransformOutputResult
            ) -> None:
                record("transform_output")

            async def before_response(self) -> None:
                record("before_response")

        return _Async

    return factory("A"), factory("B")


def _create_fn(
    harness: _Harness,
    middleware: list[UninitializedMiddleware],
    *,
    is_sync: bool,
) -> inngest.Function[typing.Any]:
    if is_sync:

        def fn_sync(ctx: inngest.ContextSync) -> str:
            return "ok"

        return harness.client.create_function(
            fn_id="fn",
            middleware=middleware,
            trigger=inngest.TriggerEvent(event="start"),
        )(fn_sync)

    async def fn_async(ctx: inngest.Context) -> str:
        return "ok"

    return harness.client.create_function(
        fn_id="fn",
        middleware=middleware,
        trigger=inngest.TriggerEvent(event="start"),
    )(fn_async)


def _before_response_calls(messages: list[str]) -> list[str]:
    return [m for m in messages if m.endswith(".before_response")]


_MODES = [("async", False), ("sync", True)]


class TestBeforeResponseGuarantees(unittest.TestCase):
    def test_runs_after_transform_output_raises(self) -> None:
        """
        A raising transform_output must not skip anyone's before_response.
        """

        for mode, is_sync in _MODES:
            with self.subTest(mode=mode):
                harness = _Harness()
                messages: list[str] = []
                fn = _create_fn(
                    harness,
                    list(
                        _create_middleware(
                            messages,
                            is_sync=is_sync,
                            raise_in={"A": "transform_output"},
                        )
                    ),
                    is_sync=is_sync,
                )

                status, body = asyncio.run(harness.request(fn))

                assert _before_response_calls(messages) == [
                    "A.before_response",
                    "B.before_response",
                ]
                assert status == 500
                assert body["message"] == "A.transform_output failed"

    def test_runs_for_all_when_one_raises(self) -> None:
        """
        One middleware's before_response raising must not skip the others.
        """

        for mode, is_sync in _MODES:
            with self.subTest(mode=mode):
                harness = _Harness()
                messages: list[str] = []
                fn = _create_fn(
                    harness,
                    list(
                        _create_middleware(
                            messages,
                            is_sync=is_sync,
                            raise_in={"A": "before_response"},
                        )
                    ),
                    is_sync=is_sync,
                )

                status, body = asyncio.run(harness.request(fn))

                assert _before_response_calls(messages) == [
                    "A.before_response",
                    "B.before_response",
                ]
                assert status == 500
                assert body["message"] == "A.before_response failed"

    def test_cleanup_errors_preserve_transform_output_error(self) -> None:
        for mode, is_sync in _MODES:
            with self.subTest(mode=mode):
                harness = _Harness()
                messages: list[str] = []
                fn = _create_fn(
                    harness,
                    list(
                        _create_middleware(
                            messages,
                            is_sync=is_sync,
                            raise_in={
                                "A": "transform_output",
                                "B": "before_response",
                            },
                        )
                    ),
                    is_sync=is_sync,
                )

                status, body = asyncio.run(harness.request(fn))

                assert status == 500
                assert body["message"] == "A.transform_output failed"
                assert harness.log_records == [
                    "before_response middleware failed: B.before_response failed"
                ]
                assert _before_response_calls(messages) == [
                    "A.before_response",
                    "B.before_response",
                ]

    def test_all_cleanup_errors_are_logged(self) -> None:
        for mode, is_sync in _MODES:
            with self.subTest(mode=mode):
                harness = _Harness()
                messages: list[str] = []
                fn = _create_fn(
                    harness,
                    list(
                        _create_middleware(
                            messages,
                            is_sync=is_sync,
                            raise_in={
                                "A": "before_response",
                                "B": "before_response",
                            },
                        )
                    ),
                    is_sync=is_sync,
                )

                status, body = asyncio.run(harness.request(fn))

                assert status == 500
                assert body["message"] == "A.before_response failed"
                assert harness.log_records == [
                    "before_response middleware failed: A.before_response failed",
                    "before_response middleware failed: B.before_response failed",
                ]
                assert _before_response_calls(messages) == [
                    "A.before_response",
                    "B.before_response",
                ]

    def test_cleanup_preserves_execution_error_and_retry_policy(self) -> None:
        for mode, is_sync in _MODES:
            for failure in ("retriable", "non-retriable", "final", "step"):
                with self.subTest(mode=mode, failure=failure):
                    harness = _Harness()
                    messages: list[str] = []

                    def fail() -> None:
                        if failure == "non-retriable":
                            raise inngest.NonRetriableError("original failure")
                        raise ValueError("original failure")

                    def sync(ctx: inngest.ContextSync) -> None:
                        if failure == "final":
                            # Used by group.sandbox after its sandbox is destroyed.
                            ctx.step._execution.fail_finally()
                        if failure == "step":
                            ctx.step.run("fail", fail)
                        else:
                            fail()

                    async def async_fn(ctx: inngest.Context) -> None:
                        if failure == "final":
                            ctx.step._execution.fail_finally()
                        if failure == "step":

                            async def fail_step() -> None:
                                fail()

                            await ctx.step.run("fail", fail_step)
                        else:
                            fail()

                    fn = harness.client.create_function(
                        fn_id="fn",
                        trigger=inngest.TriggerEvent(event="start"),
                        middleware=list(
                            _create_middleware(
                                messages,
                                is_sync=is_sync,
                                raise_in={"A": "before_response"},
                            )
                        ),
                    )(sync if is_sync else async_fn)

                    status, body = asyncio.run(harness.request(fn))

                    if failure == "step":
                        assert status == 206
                        assert body[0]["error"]["message"] == "original failure"
                    else:
                        assert status == 500
                        assert body["message"] == "original failure"
                    assert harness.response_headers.get(
                        server_lib.HeaderKey.NO_RETRY.value
                    ) == (
                        "true"
                        if failure in ("final", "non-retriable")
                        else None
                    )
                    assert harness.log_records == [
                        "before_response middleware failed: A.before_response failed"
                    ]
                    assert _before_response_calls(messages) == [
                        "A.before_response",
                        "B.before_response",
                    ]

    def test_cancellation_cleans_up_in_same_context_and_propagates(
        self,
    ) -> None:
        for phase in (
            "transform_input",
            "before_execution",
            "handler",
            "after_execution",
            "transform_output",
            "before_response",
        ):
            with self.subTest(phase=phase):
                harness = _Harness()
                messages: list[str] = []
                active = contextvars.ContextVar[str | None](
                    "active_span", default=None
                )

                async def check() -> None:
                    ready = asyncio.Event()

                    async def block_at(current: str) -> None:
                        if phase == current:
                            ready.set()
                            await asyncio.Event().wait()

                    class Trace(inngest.Middleware):
                        async def transform_input(
                            self,
                            ctx: inngest.Context | inngest.ContextSync,
                            function: inngest.Function[typing.Any],
                            steps: inngest.StepMemos,
                        ) -> None:
                            self.token = active.set("span")
                            await block_at("transform_input")

                        async def before_execution(self) -> None:
                            await block_at("before_execution")

                        async def after_execution(self) -> None:
                            await block_at("after_execution")

                        async def transform_output(
                            self, result: inngest.TransformOutputResult
                        ) -> None:
                            await block_at("transform_output")

                        async def before_response(self) -> None:
                            try:
                                await block_at("before_response")
                            finally:
                                active.reset(self.token)
                                messages.append("span ended")

                    class Broken(inngest.Middleware):
                        async def before_response(self) -> None:
                            raise ValueError("cleanup failed")

                    class Last(inngest.Middleware):
                        async def before_response(self) -> None:
                            # Cleanup must also be able to suspend after cancellation.
                            await asyncio.sleep(0)
                            messages.append("last cleanup")

                    @harness.client.create_function(
                        fn_id="fn",
                        trigger=inngest.TriggerEvent(event="start"),
                        middleware=[Trace, Broken, Last],
                    )
                    async def fn(ctx: inngest.Context) -> None:
                        await block_at("handler")

                    task = asyncio.create_task(harness.request(fn))
                    await asyncio.wait_for(ready.wait(), timeout=5)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(task, timeout=5)
                    assert task.cancelled()

                asyncio.run(check())
                assert messages == ["span ended", "last cleanup"]
                assert harness.log_records == [
                    "before_response middleware failed: cleanup failed"
                ]

    def test_sync_cleanup_continues_after_async_hook(self) -> None:
        messages: list[str] = []

        class Mixed(inngest.MiddlewareSync):
            async def before_response(self) -> None:  # type: ignore[override]
                pass

        class Last(inngest.MiddlewareSync):
            def before_response(self) -> None:
                messages.append("last cleanup")

        harness = _Harness()
        fn = _create_fn(harness, [Mixed, Last], is_sync=True)

        status, body = asyncio.run(harness.request(fn))

        assert status == 500
        assert body["name"] == "AsyncUnsupportedError"
        assert messages == ["last cleanup"]


class TestAfterSendEventsSync(unittest.TestCase):
    def test_rejects_async_after_send_events(self) -> None:
        """
        A sync-only code path must reject an async after_send_events hook
        instead of creating a coroutine that is never awaited.
        """

        class _Mixed(inngest.MiddlewareSync):
            async def after_send_events(  # type: ignore[override]
                self, result: client_lib.SendEventsResult
            ) -> None:
                pass

        harness = _Harness()
        mgr = MiddlewareManager(harness.client, None, net.ServerTimings())
        mgr.add(_Mixed)

        err = mgr.after_send_events_sync(client_lib.SendEventsResult())

        assert isinstance(err, errors.AsyncUnsupportedError)

    def test_rejects_async_hook_through_step_send_event(self) -> None:
        class Mixed(inngest.MiddlewareSync):
            async def after_send_events(  # type: ignore[override]
                self, result: client_lib.SendEventsResult
            ) -> None:
                pass

        harness = _Harness()

        @harness.client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="start"),
            middleware=[Mixed],
        )
        def fn(ctx: inngest.ContextSync) -> None:
            ctx.step.send_event("send", inngest.Event(name="other"))

        status, body = asyncio.run(harness.request(fn))

        assert status == 206
        assert body[0]["op"] == server_lib.Opcode.STEP_ERROR.value
        assert body[0]["error"]["name"] == "AsyncUnsupportedError"


class TestLoggerAfterClientSend(unittest.TestCase):
    def test_ctx_logger_works_after_client_send(self) -> None:
        """
        client.send builds its own middleware (including LoggerMiddleware).
        That must not silence ctx.logger for the rest of the execution.
        """

        for mode, is_sync in _MODES:
            with self.subTest(mode=mode):
                harness = _Harness()

                if is_sync:

                    def fn_sync(ctx: inngest.ContextSync) -> None:
                        ctx.logger.info("before send")
                        harness.client.send_sync(inngest.Event(name="other"))
                        ctx.logger.info("after send")

                    fn = harness.client.create_function(
                        fn_id="fn",
                        trigger=inngest.TriggerEvent(event="start"),
                    )(fn_sync)
                else:

                    async def fn_async(ctx: inngest.Context) -> None:
                        ctx.logger.info("before send")
                        await harness.client.send(inngest.Event(name="other"))
                        ctx.logger.info("after send")

                    fn = harness.client.create_function(
                        fn_id="fn",
                        trigger=inngest.TriggerEvent(event="start"),
                    )(fn_async)

                asyncio.run(harness.request(fn))

                assert "before send" in harness.log_records
                assert "after send" in harness.log_records


class TestReplayLogging(unittest.TestCase):
    def test_replay_resets_logging_between_requests(self) -> None:
        """In particular, reused sync workers must not retain logging-on state."""
        for mode, is_sync in _MODES:
            with self.subTest(mode=mode):
                harness = _Harness()

                def sync(ctx: inngest.ContextSync) -> None:
                    ctx.logger.info("replayed code")
                    ctx.step.run("memo", lambda: ctx.logger.info("memo body"))
                    ctx.logger.info("new code")
                    ctx.step.run("new", lambda: ctx.logger.info("new step"))

                async def async_fn(ctx: inngest.Context) -> None:
                    ctx.logger.info("replayed code")

                    async def memo() -> None:
                        ctx.logger.info("memo body")

                    async def new() -> None:
                        ctx.logger.info("new step")

                    await ctx.step.run("memo", memo)
                    ctx.logger.info("new code")
                    await ctx.step.run("new", new)

                fn = harness.client.create_function(
                    fn_id="fn",
                    trigger=inngest.TriggerEvent(event="start"),
                )(sync if is_sync else async_fn)
                handler = harness.create_handler(fn)
                if handler._thread_pool is not None:
                    handler._thread_pool.shutdown()

                # Force both sync invocations onto the same worker thread.
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=1
                ) as pool:
                    handler._thread_pool = pool

                    async def check() -> None:
                        status, _ = await harness.request(fn, handler=handler)
                        assert status == 206
                        assert harness.log_records == [
                            "replayed code",
                            "memo body",
                        ]
                        harness.log_records.clear()

                        status, body = await harness.request(
                            fn,
                            steps={
                                transforms.hash_step_id("memo"): {"data": None}
                            },
                            handler=handler,
                        )
                        assert status == 206
                        assert body[0]["id"] == transforms.hash_step_id("new")

                    asyncio.run(check())

                assert harness.log_records == ["new code", "new step"]

    def test_parallel_replay_and_step_targeting(self) -> None:
        cases = [
            (["initial", "a", "b"], None, ["after parallel", "new step"]),
            (["initial", "a"], None, []),
            (["initial", "a"], "b", ["b"]),
            (["initial"], "a", ["a"]),
        ]
        for mode, is_sync in _MODES:
            for memos, target, expected_logs in cases:
                with self.subTest(mode=mode, memos=memos, target=target):
                    harness = _Harness()

                    def sync(ctx: inngest.ContextSync) -> None:
                        ctx.logger.info("replayed code")
                        ctx.step.run(
                            "initial", lambda: ctx.logger.info("initial")
                        )
                        ctx.group.parallel(
                            (
                                lambda: ctx.step.run(
                                    "a", lambda: ctx.logger.info("a")
                                ),
                                lambda: ctx.step.run(
                                    "b", lambda: ctx.logger.info("b")
                                ),
                            )
                        )
                        ctx.logger.info("after parallel")
                        ctx.step.run("new", lambda: ctx.logger.info("new step"))

                    async def async_fn(ctx: inngest.Context) -> None:
                        ctx.logger.info("replayed code")

                        async def initial() -> None:
                            ctx.logger.info("initial")

                        async def a() -> None:
                            ctx.logger.info("a")

                        async def b() -> None:
                            ctx.logger.info("b")

                        async def new() -> None:
                            ctx.logger.info("new step")

                        await ctx.step.run("initial", initial)
                        await ctx.group.parallel(
                            (
                                lambda: ctx.step.run("a", a),
                                lambda: ctx.step.run("b", b),
                            )
                        )
                        ctx.logger.info("after parallel")
                        await ctx.step.run("new", new)

                    fn = harness.client.create_function(
                        fn_id="fn",
                        trigger=inngest.TriggerEvent(event="start"),
                    )(sync if is_sync else async_fn)
                    steps: dict[str, object] = {
                        transforms.hash_step_id(step_id): {"data": None}
                        for step_id in memos
                    }

                    status, body = asyncio.run(
                        harness.request(fn, steps=steps, target=target)
                    )

                    assert status == 206
                    assert harness.log_records == expected_logs
                    if target is not None:
                        assert [step["id"] for step in body] == [
                            transforms.hash_step_id(target)
                        ]
                    elif len(memos) == 2:
                        assert body[0]["op"] == server_lib.Opcode.PLANNED.value
