from __future__ import annotations

import asyncio
import json
import typing

import httpx
import pytest
from test_core.harness import Harness

import inngest
from inngest.experimental import experiment

from . import net


@pytest.mark.parametrize("is_sync", [False, True])
def test_experiment_discovery_replay_and_scoring(is_sync: bool) -> None:
    harness = Harness()
    select = experiment.fixed("control")
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
            select=select,
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
            select=select,
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
        nonlocal select
        memos: dict[str, object] = {}
        response, ops = await harness.request(fn)
        assert response.status_code == 206
        selection = ops[0]
        assert selection["opts"] == {"type": "group.experiment"}
        assert selection["metadata"][0]["values"] == {
            "name": "model",
            "variant": "control",
            "selection_strategy": "fixed",
            "available_variants": ["control", "variant"],
        }
        memos[selection["id"]] = {"data": selection["data"]}
        # A deployment changes both strategy and assignment. Existing runs must
        # keep their original variant and report how it was actually selected.
        select = experiment.bucket("bob")
        _, ops = await harness.request(fn, memos=memos)
        assert ops[0]["displayName"] == "control"
        assert ops[0]["opts"] == {
            "experimentName": "model",
            "variant": "control",
            "selectionStrategy": "fixed",
        }
        memos[ops[0]["id"]] = {"data": ops[0]["data"]}
        _, ops = await harness.request(fn, memos=memos)
        updates = [json.loads(request.content) for request in harness.requests]
        assert [update["metadata"][0] for update in updates] == [
            {
                "kind": "inngest.experiment",
                "op": "merge",
                "values": {"name": "model", "variant": "control"},
            },
            # Each score gets its own kind, like the TypeScript SDK.
            {
                "kind": "inngest.score.cost",
                "op": "merge",
                "values": {"value": 0.1},
            },
        ]
        assert all(
            update["target"] == {"run_id": "original"} for update in updates
        )
        assert ops[0]["opts"] is None  # Experiment context does not leak.
        memos[ops[0]["id"]] = {"data": None}
        response, result = await harness.request(fn, memos=memos)
        assert response.status_code == 200 and result == "control"
        assert calls == ["work"]
        assert (
            len(harness.requests) == 2
        )  # Replay does not repeat score writes.

    asyncio.run(check())


def test_failed_attribution_does_not_write_score() -> None:
    for is_sync in (False, True):
        harness = Harness()
        harness.status = 503
        ref = experiment.ExperimentRef(
            experiment_name="model", variant="control"
        )
        with pytest.raises(Exception, match="503"):
            if is_sync:
                harness.client.score_experiment_sync(
                    experiment=ref,
                    run_id="finished",
                    name="approved",
                    value=True,
                )
            else:
                asyncio.run(
                    harness.client.score_experiment(
                        experiment=ref,
                        run_id="finished",
                        name="approved",
                        value=True,
                    )
                )
        assert len(harness.requests) == 1
        payload = json.loads(harness.requests[0].content)
        assert payload["metadata"][0]["kind"] == "inngest.experiment"


def test_bucket_uses_relative_weights() -> None:
    # With an 80/20 split, charlie selects control and grace selects variant.
    # Using equivalent 8/2 weights must preserve both assignments.
    cases = [("charlie", "control"), ("grace", "variant")]
    for user_id, expected in cases:
        assert (
            experiment.bucket(
                user_id, weights={"control": 80, "variant": 20}
            ).choose(["control", "variant"])
            == expected
        ), f"{user_id}: 80/20 weights"
        assert (
            experiment.bucket(
                user_id, weights={"control": 8, "variant": 2}
            ).choose(["control", "variant"])
            == expected
        ), f"{user_id}: 8/2 weights"


def test_bucket_matches_typescript_fixtures() -> None:
    # TypeScript SHA-256 fixtures: alice = 2bd806c9, bob = 81b637d8.
    assert (
        experiment.bucket("alice").choose(["variant", "control"]) == "control"
    )
    assert experiment.bucket("bob").choose(["control", "variant"]) == "variant"


def test_bucket_snapshots_weights() -> None:
    weights = {"control": 0.0, "variant": 1.0}
    selector = experiment.bucket("alice", weights=weights)
    weights["control"] = 100.0
    assert selector.choose(["control", "variant"]) == "variant"


def test_bucket_rejects_invalid_weights() -> None:
    invalid_weights: list[dict[str, float]] = [
        {},
        {"control": 0},
        {"control": -1},
        {"control": float("inf")},
        {"control": float("nan")},
    ]
    for weights in invalid_weights:
        with pytest.raises(ValueError):
            experiment.bucket("alice", weights=weights)


def test_selection_rejects_empty_value() -> None:
    with pytest.raises(ValueError):
        experiment.bucket("")
    with pytest.raises(ValueError):
        experiment.fixed("")


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

    _, selection = asyncio.run(harness.request(fn))
    response, body = asyncio.run(
        harness.request(
            fn,
            memos={selection[0]["id"]: {"data": selection[0]["data"]}},
        )
    )
    assert response.status_code == 500
    assert response.no_retry
    assert "must invoke step tools" in body["message"]


def test_partial_experiment_score_failure_is_retryable() -> None:
    for is_sync in (False, True):
        harness = Harness()
        calls: list[dict[str, typing.Any]] = []

        def handle(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            return httpx.Response(503 if len(calls) == 2 else 204)

        transport = httpx.MockTransport(handle)
        harness.client._http_client._http_client_sync = httpx.Client(
            transport=transport
        )
        harness.client._http_client._http_client = (
            net.ThreadAwareAsyncHTTPClient(transport=transport).initialize()
        )
        ref = experiment.ExperimentRef(
            experiment_name="model", variant="control"
        )

        def score() -> None:
            if is_sync:
                harness.client.score_experiment_sync(
                    experiment=ref, run_id="finished", name="cost", value=1
                )
            else:
                asyncio.run(
                    harness.client.score_experiment(
                        experiment=ref, run_id="finished", name="cost", value=1
                    )
                )

        with pytest.raises(Exception, match="503"):
            score()
        score()
        assert len(calls) == 4
        assert [call["metadata"][0]["kind"] for call in calls[:2]] == [
            "inngest.experiment",
            "inngest.score.cost",
        ]
        assert calls[:2] == calls[2:]
