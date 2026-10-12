"""Property-based checkpoint replay tests against an independent durable model."""

import asyncio
import collections
import json
import os
import typing
from unittest import mock

import httpx
import pytest
from hypothesis import given, note, settings
from hypothesis import strategies as st

import inngest
from inngest._internal import net, server_lib
from inngest._internal.checkpoint import Checkpointer
from inngest._internal.checkpoint_test import request
from inngest._internal.comm_lib.handler import CommHandler

json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.text(max_size=20)
    | st.floats(allow_nan=False, allow_infinity=False),
    lambda child: st.lists(child, max_size=4)
    | st.dictionaries(st.text(max_size=8), child, max_size=4),
    max_leaves=12,
)


@pytest.mark.parametrize("sync", [True, False])
@settings(
    max_examples=int(os.getenv("CHECKPOINT_PROPERTY_EXAMPLES", "200")),
    deadline=None,
)
@given(
    steps=st.lists(
        st.tuples(st.sampled_from(["a", "same", "a:b", "😀"]), json_values),
        min_size=1,
        max_size=12,
    ),
    faults=st.lists(
        st.sampled_from(["ok", "reject", "commit_then_timeout", "timeout"]),
        min_size=1,
        max_size=8,
    ),
    dropped_responses=st.lists(st.booleans(), max_size=3),
    wrap=st.booleans(),
)
def test_replay_matches_durable_model(
    sync: bool,
    steps: list[tuple[str, object]],
    faults: list[str],
    dropped_responses: list[bool],
    wrap: bool,
) -> None:
    # This oracle models only durable storage, not SDK control flow or hashing.
    durable: dict[str, object] = {}
    confirmed: set[int] = set()
    callbacks: collections.Counter[int] = collections.Counter()
    requests = 0

    def decode(value: object) -> typing.Any:
        return (
            typing.cast(dict[str, object], value)["wrapped"] if wrap else value
        )

    def save(step: dict[str, typing.Any]) -> None:
        identity, value = step["id"], step["data"]
        if identity in durable:
            assert durable[identity] == {"data": value}
        durable[identity] = {"data": value}
        confirmed.add(decode(value)["index"])

    def transport(req: httpx.Request) -> httpx.Response:
        nonlocal requests
        fault = faults[requests % len(faults)]
        requests += 1
        if fault == "reject":
            return httpx.Response(404)
        if fault in ("ok", "commit_then_timeout"):
            for step in json.loads(req.content)["steps"]:
                save(step)
        if fault in ("commit_then_timeout", "timeout"):
            raise httpx.ReadTimeout("injected checkpoint network fault")
        return httpx.Response(200)

    class Wrapper(inngest.MiddlewareSync):
        def transform_output(
            self, result: inngest.TransformOutputResult
        ) -> None:
            if wrap and result.step is not None:
                result.output = {"wrapped": result.output}

        def transform_input(
            self,
            ctx: inngest.Context | inngest.ContextSync,
            function: inngest.Function[typing.Any],
            memos: inngest.StepMemos,
        ) -> None:
            if wrap:
                for memo in memos.values():
                    memo.data = decode(memo.data)

    client = inngest.Inngest(
        app_id="test",
        is_production=False,
        checkpointing=True,
        middleware=[Wrapper],
    )
    # Close the default transports before installing test-only ones.
    client._http_client._http_client_sync.close()
    asyncio.run(client._http_client._http_client.aclose())
    client._http_client._http_client_sync = httpx.Client(
        transport=httpx.MockTransport(transport)
    )
    client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
        transport=httpx.MockTransport(transport)
    ).initialize()

    def callback(index: int, value: object) -> object:
        assert index not in confirmed, "A durable step was executed again"
        callbacks[index] += 1
        return {"index": index, "value": value}

    def fn_sync(ctx: inngest.ContextSync) -> list[object]:
        return [
            ctx.step.run(name, callback, i, value)
            for i, (name, value) in enumerate(steps)
        ]

    async def fn_async(ctx: inngest.Context) -> list[object]:
        async def cb(index: int, value: object) -> object:
            return callback(index, value)

        return [
            await ctx.step.run(name, cb, i, value)
            for i, (name, value) in enumerate(steps)
        ]

    fn = client.create_function(
        fn_id="fn",
        trigger=inngest.TriggerEvent(event="test"),
    )(fn_sync if sync else fn_async)
    handler = CommHandler(
        client=client,
        functions=[fn],
        framework=server_lib.Framework.FAST_API,
        enable_unauthed_sync=None,
        streaming=None,
    )
    original_delay = Checkpointer._retry_delay

    def no_delay(
        self: Checkpointer, response: httpx.Response | Exception, attempt: int
    ) -> float | None:
        delay = original_delay(self, response, attempt)
        return None if delay is None else 0

    async def run() -> None:
        # Every successful response advances at least one step. Lost responses
        # consume a finite fault budget. There must be a bounded completion.
        for invocation in range(len(steps) + len(dropped_responses) + 2):
            req = request()
            body = json.loads(req.body)
            body["steps"] = durable
            req.body = json.dumps(body).encode()
            response = (
                handler.post_sync(req) if sync else await handler.post(req)
            )
            note(
                f"invocation={invocation} status={response.status_code} durable={len(durable)}"
            )
            if (
                invocation < len(dropped_responses)
                and dropped_responses[invocation]
            ):
                # Simulate losing the entire worker response. Only independently
                # checkpointed state may survive, never this response's data.
                continue
            if response.status_code == 200:
                assert response.body == [
                    {"index": i, "value": value}
                    for i, (_, value) in enumerate(steps)
                ]
                assert len(durable) == len(steps)
                assert confirmed == set(range(len(steps)))
                assert all(count >= 1 for count in callbacks.values())
                return
            assert response.status_code == 206, response.body
            for step in typing.cast(list[dict[str, typing.Any]], response.body):
                assert step["op"] == "StepRun"
                save(step)
        pytest.fail("Execution did not make bounded progress")

    try:
        with mock.patch.object(Checkpointer, "_retry_delay", no_delay):
            asyncio.run(run())
    finally:
        if handler._thread_pool is not None:
            handler._thread_pool.shutdown()
        client._http_client._http_client_sync.close()
        asyncio.run(client._http_client._http_client.aclose())
