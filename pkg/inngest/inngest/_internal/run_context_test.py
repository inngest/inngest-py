from __future__ import annotations

import asyncio
import datetime

import pytest
from test_core.harness import Harness

import inngest
from inngest.experimental.ai import openai

from .run_context import Span, SpanScope, current_span


def _ids() -> list[str]:
    return [s.id for s in current_span.get()]


def test_nested_spans_form_a_path() -> None:
    with SpanScope("outer"), SpanScope("inner"):
        assert _ids() == ["outer", "inner"]
    assert current_span.get() == ()


def test_inner_span_inherits_origin() -> None:
    with SpanScope("outer", origin="lib@1.0"):
        with SpanScope("inner"):
            assert current_span.get()[-1].origin == "lib@1.0"
        with SpanScope("inner", origin="other@2.0"):
            assert current_span.get()[-1].origin == "other@2.0"


def test_span_resets_after_exception() -> None:
    with pytest.raises(ValueError), SpanScope("agent"):
        raise ValueError("boom")
    assert current_span.get() == ()


def test_scope_nested_in_itself() -> None:
    scope = SpanScope("agent")
    with scope:
        with scope:
            assert _ids() == ["agent", "agent"]
        assert _ids() == ["agent"]
    assert current_span.get() == ()


def test_reused_scope_inherits_each_parents_origin() -> None:
    scope = SpanScope("child")
    with SpanScope("p1", origin="x@1"), scope:
        assert current_span.get()[-1].origin == "x@1"
    with SpanScope("p2", origin="y@2"), scope:
        assert current_span.get()[-1].origin == "y@2"
    with scope:
        assert current_span.get()[-1].origin is None
    assert current_span.get() == ()


def test_scope_shared_across_concurrent_tasks() -> None:
    scope = SpanScope("agent")
    seen: list[list[str]] = []

    async def task(child: str) -> None:
        with scope:
            await asyncio.sleep(0)
            with SpanScope(child):
                await asyncio.sleep(0)
                seen.append(_ids())
            await asyncio.sleep(0)
        assert current_span.get() == ()

    async def main() -> None:
        await asyncio.gather(task("a"), task("b"))

    asyncio.run(main())
    assert sorted(seen) == [["agent", "a"], ["agent", "b"]]
    assert current_span.get() == ()


@pytest.mark.parametrize("is_sync", [False, True])
def test_steps_report_span_on_the_wire(is_sync: bool) -> None:
    harness = Harness()
    # The async handler runs in its own task (copied context), so the test's
    # current_span can't show a leak. Record it inside the handler instead, in
    # a finally so exits caused by a step interrupt are observed too.
    after_block: list[tuple[Span, ...]] = []

    def sync_fn(ctx: inngest.ContextSync) -> None:
        try:
            with ctx.group._span("agent", name="Research", kind="agent"):
                ctx.step.run("model", lambda: None)
        finally:
            after_block.append(current_span.get())
        ctx.step.run("after", lambda: None)

    async def async_fn(ctx: inngest.Context) -> None:
        async def work() -> None:
            pass

        try:
            with ctx.group._span("agent", name="Research", kind="agent"):
                await ctx.step.run("model", work)
        finally:
            after_block.append(current_span.get())
        await ctx.step.run("after", work)

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(sync_fn if is_sync else async_fn)

    async def check() -> None:
        _, ops = await harness.request(fn)
        assert ops[0]["displayName"] == "model"
        assert ops[0]["opts"] == {
            "span": [{"id": "agent", "name": "Research", "kind": "agent"}]
        }
        assert len(after_block) > 0
        assert all(v == () for v in after_block)
        after_block.clear()

        memos: dict[str, object] = {ops[0]["id"]: {"data": None}}
        _, ops = await harness.request(fn, memos=memos)
        assert ops[0]["displayName"] == "after"
        assert ops[0]["opts"] is None
        assert len(after_block) > 0
        assert all(v == () for v in after_block)

    asyncio.run(check())


@pytest.mark.parametrize("is_sync", [False, True])
def test_reused_scope_stamps_each_block_on_the_wire(is_sync: bool) -> None:
    harness = Harness()

    def sync_fn(ctx: inngest.ContextSync) -> None:
        scope = ctx.group._span("agent")
        with scope:
            ctx.step.run("first", lambda: None)
        with scope:
            ctx.step.run("second", lambda: None)

    async def async_fn(ctx: inngest.Context) -> None:
        async def work() -> None:
            pass

        scope = ctx.group._span("agent")
        with scope:
            await ctx.step.run("first", work)
        with scope:
            await ctx.step.run("second", work)

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(sync_fn if is_sync else async_fn)

    async def check() -> None:
        _, ops = await harness.request(fn)
        assert ops[0]["displayName"] == "first"
        assert ops[0]["opts"] == {"span": [{"id": "agent", "name": "agent"}]}

        memos: dict[str, object] = {ops[0]["id"]: {"data": None}}
        _, ops = await harness.request(fn, memos=memos)
        assert ops[0]["displayName"] == "second"
        assert ops[0]["opts"] == {"span": [{"id": "agent", "name": "agent"}]}

    asyncio.run(check())


@pytest.mark.parametrize("is_sync", [False, True])
def test_steps_report_nested_spans_and_origin_on_the_wire(
    is_sync: bool,
) -> None:
    harness = Harness()

    def sync_fn(ctx: inngest.ContextSync) -> None:
        with (
            ctx.group._span("outer", origin="lib@1.0"),
            ctx.group._span("inner"),
        ):
            ctx.step.run("model", lambda: None)

    async def async_fn(ctx: inngest.Context) -> None:
        async def work() -> None:
            pass

        with (
            ctx.group._span("outer", origin="lib@1.0"),
            ctx.group._span("inner"),
        ):
            await ctx.step.run("model", work)

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(sync_fn if is_sync else async_fn)

    async def check() -> None:
        _, ops = await harness.request(fn)
        assert ops[0]["displayName"] == "model"
        assert ops[0]["opts"] == {
            "span": [
                {"id": "outer", "name": "outer", "origin": "lib@1.0"},
                {"id": "inner", "name": "inner", "origin": "lib@1.0"},
            ],
            "origin": "lib@1.0",
        }

    asyncio.run(check())


@pytest.mark.parametrize("is_sync", [False, True])
def test_step_origin_overrides_span_origin(is_sync: bool) -> None:
    harness = Harness()

    def sync_fn(ctx: inngest.ContextSync) -> None:
        with ctx.group._span("agent", origin="lib@1.0"):
            ctx.step._run("model", lambda: None, origin="step@2.0")

    async def async_fn(ctx: inngest.Context) -> None:
        async def work() -> None:
            pass

        with ctx.group._span("agent", origin="lib@1.0"):
            await ctx.step._run("model", work, origin="step@2.0")

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(sync_fn if is_sync else async_fn)

    async def check() -> None:
        _, ops = await harness.request(fn)
        assert ops[0]["opts"] == {
            "span": [{"id": "agent", "name": "agent", "origin": "lib@1.0"}],
            "origin": "step@2.0",
        }

    asyncio.run(check())


_STEP_TYPES = [
    "run",
    "send-event",
    "sleep",
    "sleep-until",
    "wait-for-event",
    "invoke",
    "infer",
]


@pytest.mark.parametrize("is_sync", [False, True])
def test_every_step_type_reports_span(is_sync: bool) -> None:
    harness = Harness()
    adapter = openai.Adapter(auth_key="key", model="gpt")
    until = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
    event = inngest.Event(name="other")

    def sync_fn(ctx: inngest.ContextSync) -> None:
        step = ctx.step
        with ctx.group._span("agent"):
            ctx.group.parallel(
                (
                    lambda: step.run("run", lambda: None),
                    lambda: step.send_event("send-event", event),
                    lambda: step.sleep("sleep", 1000),
                    lambda: step.sleep_until("sleep-until", until),
                    lambda: step.wait_for_event(
                        "wait-for-event", event="other", timeout=1000
                    ),
                    lambda: step.invoke_by_id("invoke", function_id="other"),
                    lambda: step.ai.infer("infer", adapter=adapter, body={}),
                )
            )

    async def async_fn(ctx: inngest.Context) -> None:
        async def work() -> None:
            pass

        step = ctx.step
        with ctx.group._span("agent"):
            await ctx.group.parallel(
                (
                    lambda: step.run("run", work),
                    lambda: step.send_event("send-event", event),
                    lambda: step.sleep("sleep", 1000),
                    lambda: step.sleep_until("sleep-until", until),
                    lambda: step.wait_for_event(
                        "wait-for-event", event="other", timeout=1000
                    ),
                    lambda: step.invoke_by_id("invoke", function_id="other"),
                    lambda: step.ai.infer("infer", adapter=adapter, body={}),
                )
            )

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(sync_fn if is_sync else async_fn)

    async def check() -> None:
        _, ops = await harness.request(fn)
        spans = {op["displayName"]: op["opts"]["span"] for op in ops}
        assert spans == {
            t: [{"id": "agent", "name": "agent"}] for t in _STEP_TYPES
        }

    asyncio.run(check())
