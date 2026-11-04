"""
Replays through the real SDK, in process, with a client that has no
serializer: stored steps come back as plain JSON.
"""

from __future__ import annotations

import asyncio
import time
import typing

import inngest
import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from test_core.harness import Harness

from . import const
from .fakes_test import Counters, ScriptedModel, call, make_tools, tool_turn
from .middleware import InngestMiddleware, durable

INPUT: typing.Any = {"messages": [HumanMessage("hi")]}

modes = pytest.mark.parametrize("is_sync", [False, True], ids=["async", "sync"])


class Out(BaseModel):
    text: str


async def run_to_completion(
    harness: Harness, fn: inngest.Function[typing.Any]
) -> tuple[object, list[dict[str, typing.Any]]]:
    """Play Inngest: request until the function returns. Returns its output
    and every step op, in order."""

    memos: dict[str, object] = {}
    seen: list[dict[str, typing.Any]] = []
    for _ in range(50):
        response, body = await harness.request(fn, memos=memos)
        if response.status_code == 200:
            return body, seen
        for op in body:
            if op["op"] == "StepPlanned":
                _, ops = await harness.request(
                    fn, memos=memos, step_id=op["id"]
                )
                op = ops[0]
            assert op["op"] == "StepRun", op
            memos[op["id"]] = {"data": op["data"]}
            seen.append(op)
    raise AssertionError("replay cap hit")


def agent_script(agent_id: str) -> list[AIMessage | Exception]:
    return [
        tool_turn(
            call("weather", f"{agent_id}_1", city="Paris"),
            call("local_time", f"{agent_id}_2", city="Paris"),
        ),
        AIMessage(content=f"from {agent_id}"),
    ]


@modes
def test_structured_response_without_serializer(is_sync: bool) -> None:
    harness = Harness()
    c = Counters()
    script: list[AIMessage | Exception] = [
        tool_turn(call("weather", "call_1", city="Paris")),
        tool_turn(call("Out", "call_2", text="hi")),
    ]

    def agent(ctx: inngest.Context | inngest.ContextSync) -> typing.Any:
        return durable(
            create_agent(
                ScriptedModel(script=script, counters=c),
                make_tools(c),
                middleware=[InngestMiddleware(ctx, name="Agent")],
                response_format=ToolStrategy(Out),
            )
        )

    def fn_sync(ctx: inngest.ContextSync) -> str:
        result = agent(ctx).invoke(INPUT)
        assert isinstance(result["structured_response"], Out)
        return result["structured_response"].text

    async def fn_async(ctx: inngest.Context) -> str:
        result = await agent(ctx).ainvoke(INPUT)
        assert isinstance(result["structured_response"], Out)
        return result["structured_response"].text

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(fn_sync if is_sync else fn_async)

    output, ops = asyncio.run(run_to_completion(harness, fn))
    assert output == "hi"
    assert [op["name"] for op in ops] == [
        "agent/model-0",
        "agent/tool-call_1",
        "agent/model-1",
    ]
    assert c.model == 2 and c.tools["weather"] == 1
    agent_span = {"id": "agent", "name": "Agent", "kind": "agent"}
    assert ops[0]["opts"] == {
        "span": [
            agent_span,
            {
                "id": "agent/model-0",
                "name": "ScriptedModel",
                "kind": "llm",
                "origin": const.ORIGIN,
            },
        ],
        "origin": const.ORIGIN,
    }
    assert ops[1]["opts"]["span"][1] == {
        "id": "agent/tool-call_1",
        "name": "weather",
        "kind": "tool",
        "origin": const.ORIGIN,
    }


def _agent(
    ctx: inngest.Context | inngest.ContextSync,
    c: dict[str, Counters],
    agent_id: str,
) -> typing.Any:
    return durable(
        create_agent(
            ScriptedModel(
                script=agent_script(agent_id),
                counters=c[agent_id],
                by_turn=True,
            ),
            make_tools(c[agent_id]),
            middleware=[InngestMiddleware(ctx, agent_id=agent_id)],
        )
    )


def _two_agents_sync(
    c: dict[str, Counters], how: str
) -> typing.Callable[[inngest.ContextSync], list[str]]:
    def fn(ctx: inngest.ContextSync) -> list[str]:
        def run(agent_id: str) -> str:
            result = _agent(ctx, c, agent_id).invoke(INPUT)
            return str(result["messages"][-1].content)

        assert how == "parallel"
        return list(ctx.group.parallel((lambda: run("a"), lambda: run("b"))))

    return fn


def _two_agents_async(
    c: dict[str, Counters], how: str
) -> typing.Callable[[inngest.Context], typing.Awaitable[list[str]]]:
    async def fn(ctx: inngest.Context) -> list[str]:
        async def run(agent_id: str) -> str:
            result = await _agent(ctx, c, agent_id).ainvoke(INPUT)
            return str(result["messages"][-1].content)

        if how == "parallel":
            return list(
                await ctx.group.parallel((lambda: run("a"), lambda: run("b")))
            )
        return list(await asyncio.gather(run("a"), run("b")))

    return fn


@pytest.mark.parametrize(
    ("is_sync", "how"),
    [(False, "parallel"), (True, "parallel"), (False, "gather")],
)
def test_two_agents_concurrently(is_sync: bool, how: str) -> None:
    harness = Harness()
    c = {"a": Counters(), "b": Counters()}
    create = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )
    fn: inngest.Function[typing.Any]
    if is_sync:
        fn = create(_two_agents_sync(c, how))
    else:
        fn = create(_two_agents_async(c, how))

    output, ops = asyncio.run(run_to_completion(harness, fn))
    assert output == ["from a", "from b"]
    names = [op["name"] for op in ops]
    for agent_id in "ab":
        steps = [n for n in names if n.startswith(f"{agent_id}/")]
        assert sorted(steps) == [
            f"{agent_id}/model-0",
            f"{agent_id}/model-1",
            f"{agent_id}/tool-{agent_id}_1",
            f"{agent_id}/tool-{agent_id}_2",
        ]
        if how == "parallel":
            assert c[agent_id].model == 2
            assert dict(c[agent_id].tools) == {"weather": 1, "local_time": 1}
        # With asyncio.gather, both agents can start a step in one request.
        # The SDK reports one and the other runs again later.
    assert len(names) == len(set(names))


class _Delay(AgentMiddleware[typing.Any, typing.Any, typing.Any]):
    """Delays one tool's calls while `phase` matches, to reorder arrivals."""

    def __init__(self, tool: str, when: str, phase: list[str]) -> None:
        super().__init__()
        self._tool, self._when, self._phase = tool, when, phase

    def _delay(self, request: typing.Any) -> float:
        hit = request.tool_call["name"] == self._tool
        return 0.2 if hit and self._phase[0] == self._when else 0

    def wrap_tool_call(
        self, request: typing.Any, handler: typing.Any
    ) -> typing.Any:
        time.sleep(self._delay(request))
        return handler(request)

    async def awrap_tool_call(
        self, request: typing.Any, handler: typing.Any
    ) -> typing.Any:
        await asyncio.sleep(self._delay(request))
        return await handler(request)


@modes
@pytest.mark.timeout(30)
@pytest.mark.parametrize("delayed", ["weather", "local_time"])
@pytest.mark.parametrize("when", ["discovery", "target"])
def test_targeted_replay_with_reordered_arrival(
    is_sync: bool, when: str, delayed: str
) -> None:
    """
    In `ctx.group.parallel`, Inngest plans each step and then requests it by
    ID. A slow outer middleware can change which tool call reaches its step
    first between those requests; each tool still runs once.
    """

    harness = Harness()
    c = {"agent": Counters()}
    phase = ["discovery"]

    def agent(ctx: inngest.Context | inngest.ContextSync) -> typing.Any:
        return durable(
            create_agent(
                ScriptedModel(
                    script=agent_script("agent"),
                    counters=c["agent"],
                    by_turn=True,
                ),
                make_tools(c["agent"]),
                middleware=[
                    _Delay(delayed, when, phase),
                    InngestMiddleware(ctx),
                ],
            )
        )

    def fn_sync(ctx: inngest.ContextSync) -> list[str]:
        def run() -> str:
            return str(agent(ctx).invoke(INPUT)["messages"][-1].content)

        return list(ctx.group.parallel((run,)))

    async def fn_async(ctx: inngest.Context) -> list[str]:
        async def run() -> str:
            result = await agent(ctx).ainvoke(INPUT)
            return str(result["messages"][-1].content)

        return list(await ctx.group.parallel((run,)))

    fn = harness.client.create_function(
        fn_id="fn", trigger=inngest.TriggerEvent(event="start")
    )(fn_sync if is_sync else fn_async)

    async def drive() -> object:
        memos: dict[str, object] = {}
        for _ in range(30):
            phase[0] = "discovery"
            response, body = await harness.request(fn, memos=memos)
            if response.status_code == 200:
                return body
            for op in body:
                if op["op"] == "StepPlanned":
                    phase[0] = "target"
                    _, ops = await harness.request(
                        fn, memos=memos, step_id=op["id"]
                    )
                    assert [o["id"] for o in ops] == [op["id"]], ops
                    op = ops[0]
                assert op["op"] == "StepRun", op
                memos[op["id"]] = {"data": op["data"]}
        raise AssertionError("replay cap hit")

    assert asyncio.run(drive()) == ["from agent"]
    assert dict(c["agent"].tools) == {"weather": 1, "local_time": 1}
