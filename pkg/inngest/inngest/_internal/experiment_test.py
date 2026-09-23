from __future__ import annotations

import asyncio
import json
import typing

import httpx
import pytest

import inngest
from inngest.experimental import experiment

from . import comm_lib, net, run_context, server_lib, transforms


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
            assert run_context.current_step.get() is None
            assert run_context.current_experiment.get() is None
            return response.status_code, json.loads(encoded)
        finally:
            if handler._thread_pool is not None:
                handler._thread_pool.shutdown()


@pytest.mark.parametrize("is_sync", [False, True])
def test_experiment_discovery_replay_and_scoring(is_sync: bool) -> None:
    harness = Harness()
    selected = "control"
    calls: list[str] = []

    def sync(ctx: inngest.ContextSync) -> str:
        def work() -> str:
            calls.append("work")
            return "result"

        result = ctx.group.experiment(
            "model",
            variants={
                "control": lambda: ctx.step.run("control", work),
                "variant": lambda: ctx.step.run("variant", work),
            },
            select=experiment.fixed(selected),
        )
        ctx.step.run(
            "score",
            lambda: harness.client.score_experiment_sync(
                experiment=result.experiment_ref,
                run_id=ctx.run_id,
                name="cost",
                value=0.1,
            ),
        )
        return result.variant

    async def async_fn(ctx: inngest.Context) -> str:
        async def work() -> str:
            calls.append("work")
            return "result"

        result = await ctx.group.experiment(
            "model",
            variants={
                "control": lambda: ctx.step.run("control", work),
                "variant": lambda: ctx.step.run("variant", work),
            },
            select=experiment.fixed(selected),
        )
        await ctx.step.run(
            "score",
            lambda: harness.client.score_experiment(
                experiment=result.experiment_ref,
                run_id=ctx.run_id,
                name="cost",
                value=0.1,
            ),
        )
        return result.variant

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(sync if is_sync else async_fn)

    async def check() -> None:
        nonlocal selected
        memos: dict[str, object] = {}
        status, ops = await harness.request(fn)
        assert status == 206
        selection = ops[0]
        assert selection["opts"] == {"type": "group.experiment"}
        assert selection["metadata"][0]["values"] == {
            "name": "model",
            "variant": "control",
            "selection_strategy": "fixed",
            "available_variants": ["control", "variant"],
        }
        memos[selection["id"]] = {"data": selection["data"]}
        selected = (
            "variant"  # Changed configuration must not reassign this run.
        )
        _, ops = await harness.request(fn, memos=memos)
        assert ops[0]["displayName"] == "control"
        assert ops[0]["opts"] == {
            "experimentStepID": "",
            "experimentName": "model",
            "variant": "control",
            "selectionStrategy": "fixed",
        }
        memos[ops[0]["id"]] = {"data": ops[0]["data"]}
        _, ops = await harness.request(fn, memos=memos)
        updates = [json.loads(request.content) for request in harness.requests]
        assert [update["metadata"][0]["kind"] for update in updates] == [
            "inngest.experiment",
            "inngest.score",
        ]
        assert all(
            update["target"] == {"run_id": "original"} for update in updates
        )
        assert ops[0]["opts"] is None  # Experiment context does not leak.
        memos[ops[0]["id"]] = {"data": None}
        status, result = await harness.request(fn, memos=memos)
        assert status == 200 and result == "control"
        assert calls == ["work"]
        assert (
            len(harness.requests) == 2
        )  # Replay does not repeat score writes.

    asyncio.run(check())


def test_score_api_failure_and_delayed_experiment() -> None:
    harness = Harness()
    ref = experiment.ExperimentRef(experiment_name="model", variant="control")
    harness.client.score_experiment_sync(
        experiment=ref, run_id="finished", name="approved", value=True
    )
    payloads = [json.loads(request.content) for request in harness.requests]
    assert [p["metadata"][0]["kind"] for p in payloads] == [
        "inngest.experiment",
        "inngest.score",
    ]
    assert all(p["target"] == {"run_id": "finished"} for p in payloads)
    harness.status = 503
    with pytest.raises(Exception, match="503"):
        harness.client.score_experiment_sync(
            experiment=ref, run_id="finished", name="approved", value=True
        )
    assert (
        len(harness.requests) == 3
    )  # Failed attribution must not write a bare score.


def test_bucket_fixtures_and_validation() -> None:
    # TypeScript SHA-256 fixtures: alice = 2bd806c9, bob = 81b637d8.
    assert (
        experiment.bucket("alice").choose(["variant", "control"]) == "control"
    )
    assert experiment.bucket("bob").choose(["control", "variant"]) == "variant"
    weights = {"control": 0.0, "variant": 1.0}
    selector = experiment.bucket("alice", weights=weights)
    weights["control"] = 100.0
    assert selector.choose(["control", "variant"]) == "variant"
    invalid_weights: list[dict[str, float]] = [
        {},
        {"control": 0},
        {"control": -1},
        {"control": float("inf")},
    ]
    for invalid in invalid_weights:
        with pytest.raises(ValueError):
            experiment.bucket("alice", weights=invalid)
    with pytest.raises(ValueError):
        experiment.bucket("")


def test_experiment_requires_durable_variant() -> None:
    harness = Harness()

    @harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )
    def fn(ctx: inngest.ContextSync) -> None:
        ctx.group.experiment(
            "model",
            variants={"control": lambda: "unsafe"},
            select=experiment.fixed("control"),
        )

    status, body = asyncio.run(
        harness.request(
            fn, memos={transforms.hash_step_id("model"): {"data": "control"}}
        )
    )
    assert status == 500
    assert "must invoke step tools" in body["message"]


def test_partial_experiment_score_failure_is_retryable() -> None:
    harness = Harness()
    calls: list[dict[str, typing.Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(503 if len(calls) == 2 else 204)

    harness.client._http_client._http_client_sync = httpx.Client(
        transport=httpx.MockTransport(handle)
    )
    ref = experiment.ExperimentRef(experiment_name="model", variant="control")
    with pytest.raises(Exception, match="503"):
        harness.client.score_experiment_sync(
            experiment=ref, run_id="finished", name="cost", value=1
        )
    harness.client.score_experiment_sync(
        experiment=ref, run_id="finished", name="cost", value=1
    )
    assert calls[:2] == calls[2:]
    assert all(call["target"] == {"run_id": "finished"} for call in calls)
