"""
Replay tests for `InngestMiddleware`.

Each request builds a new context, middleware and agent on one `FakeRun`, the
way Inngest replays a function from the top, until no `ResponseInterrupt`
escapes. Most tests run in both modes.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import gc
import time
import typing
import warnings

import inngest
import pytest
from inngest._internal.run_context import Span
from inngest._internal.step_lib import ResponseInterrupt
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelFallbackMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.types import Command
from pydantic import BaseModel

from . import const
from .fakes_test import (
    INPUT,
    Counters,
    FakeRun,
    Result,
    Script,
    ScriptedModel,
    call,
    context,
    drive,
    invoke,
    loop_problems,
    make_tools,
    middleware,
    three_calls_script,
    tool_turn,
)
from .middleware import InngestMiddleware, durable

EXPECTED = [
    "agent/model-0",
    "agent/tool-call_1",
    "agent/tool-call_2",
    "agent/tool-call_3",
    "agent/model-1",
]

modes = pytest.mark.parametrize("is_sync", [False, True], ids=["async", "sync"])


@pytest.fixture(autouse=True)
def _no_loop_problems() -> typing.Iterator[None]:
    loop_problems.clear()
    yield
    assert loop_problems == []


class State(AgentState[typing.Any]):
    extra_key: int


class Out(BaseModel):
    text: str


def same_ctx(mw: InngestMiddleware, agent_id: str) -> InngestMiddleware:
    """Another middleware on the same request's context."""

    return InngestMiddleware(mw._ctx, agent_id=agent_id)


def cmd_tools(
    counters: Counters, update: dict[str, object]
) -> typing.Callable[[], list[BaseTool]]:
    @tool
    def cmd() -> Command[typing.Any]:
        """cmd"""
        counters.tools["cmd"] += 1
        return Command(update=update)

    return lambda: [cmd]


def cmd_script(final: AIMessage) -> Script:
    return [tool_turn(call("cmd", "call_1")), final]


def failing_and_slow_tools(c: Counters) -> typing.Callable[[], list[BaseTool]]:
    """`fail` always raises; `slow` takes a while."""

    @tool
    def fail() -> str:
        """fail"""
        c.tools["fail"] += 1
        raise ValueError("boom")

    @tool
    def slow() -> str:
        """slow"""
        c.tools["slow"] += 1
        time.sleep(0.2)
        return "ok"

    return lambda: [fail, slow]


FAIL_THEN_SLOW: Script = [
    tool_turn(call("fail", "call_1"), call("slow", "call_2")),
    AIMessage(content="fin"),
]


@modes
def test_replay_memoizes_model_and_tools(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    res, exc, n = drive(
        run, is_sync, list(three_calls_script()), lambda: make_tools(c), c
    )
    assert exc is None and res is not None
    assert run.order == EXPECTED
    assert n == len(EXPECTED)
    assert all(v == 1 for v in run.exec_count.values())
    assert c.model == 2
    assert dict(c.tools) == {"local_time": 1, "weather": 2}
    msgs = res["messages"]
    ai = next(m for m in msgs if isinstance(m, AIMessage))
    assert [t["id"] for t in ai.tool_calls] == ["call_1", "call_2", "call_3"]
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_msgs] == ["call_1", "call_2", "call_3"]
    assert msgs[-1].content == "All done: greeting."


@modes
def test_only_interrupt_escapes_with_parallel_tools(is_sync: bool) -> None:
    escaped: list[type] = []
    for _ in range(10):
        c, run = Counters(), FakeRun()
        for _ in range(20):
            mw = middleware(run, is_sync)
            agent = durable(
                create_agent(
                    ScriptedModel(
                        script=list(three_calls_script()), counters=c
                    ),
                    make_tools(c),
                    middleware=[mw],
                )
            )
            try:
                invoke(agent, mw)
                break
            except BaseException as exc:
                escaped.append(type(exc))
    assert escaped
    assert set(escaped) == {ResponseInterrupt}


@modes
def test_tool_command_update_is_recorded(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    update: dict[str, object] = {
        "messages": [ToolMessage(content="ok", tool_call_id="call_1")],
        "extra_key": 123,
    }
    res, exc, _ = drive(
        run,
        is_sync,
        cmd_script(AIMessage(content="fin")),
        cmd_tools(c, update),
        c,
        state_schema=State,
        data={"messages": [HumanMessage("hi")], "extra_key": 0},
    )
    assert exc is None and res is not None
    assert res["extra_key"] == 123
    assert c.tools["cmd"] == 1
    assert run.order == ["agent/model-0", "agent/tool-call_1", "agent/model-1"]
    tool_msgs = [m for m in res["messages"] if isinstance(m, ToolMessage)]
    assert [m.content for m in tool_msgs] == ["ok"]


@modes
@pytest.mark.parametrize(
    ("routing", "match"),
    [
        pytest.param(True, "routing", id="goto"),
        pytest.param(False, "JSON", id="non-json"),
    ],
)
def test_unrecordable_command_is_rejected(
    is_sync: bool, routing: bool, match: str
) -> None:
    c, run = Counters(), FakeRun()
    msgs = [ToolMessage(content="ok", tool_call_id="call_1")]
    if routing:
        result = Command(goto="model", update={"messages": msgs})
    else:
        result = Command(update={"messages": msgs, "blob": object()})

    @tool
    def cmd() -> Command[typing.Any]:
        """cmd"""
        c.tools["cmd"] += 1
        return result

    res, exc, _ = drive(
        run,
        is_sync,
        cmd_script(AIMessage(content="fin")),
        lambda: [cmd],
        c,
        state_schema=State,
        data={"messages": [HumanMessage("hi")], "extra_key": 0},
    )
    assert res is None
    assert isinstance(exc, inngest.NonRetriableError)
    assert match in str(exc)
    assert "agent/tool-call_1" not in run.memo


@modes
def test_structured_output_call_beside_a_tool_call(is_sync: bool) -> None:
    """
    A `ToolStrategy` call is answered by the model node, not sent to tools.
    The `weather` call after it still runs.
    """

    c, run = Counters(), FakeRun()
    script: Script = [
        tool_turn(
            call("Out", "call_1", text="hi"),
            call("weather", "call_2", city="Paris"),
        ),
        tool_turn(call("Out", "call_3", text="bye")),
    ]
    res, exc, _ = drive(
        run,
        is_sync,
        script,
        lambda: make_tools(c),
        c,
        response_format=ToolStrategy(Out),
    )
    assert exc is None and res is not None
    assert isinstance(res["structured_response"], Out)
    assert c.tools["weather"] == 1
    assert "agent/tool-call_2" in run.order


def _boom(city: str) -> str:
    raise ValueError(f"boom {city}")


@modes
def test_tool_error_becomes_step_error_after_retries(is_sync: bool) -> None:
    c, run = Counters(), FakeRun(max_attempts=3)
    res, exc, _ = drive(
        run,
        is_sync,
        list(three_calls_script()),
        lambda: make_tools(c, _boom),
        c,
        cap=30,
    )
    assert res is None
    assert isinstance(exc, inngest.StepError)
    assert "boom Paris" in str(exc)
    assert c.tools["local_time"] == 3
    assert c.model == 1
    # Each other step runs at most once.
    others = {
        s: n for s, n in run.exec_count.items() if s != "agent/tool-call_1"
    }
    assert all(n == 1 for n in others.values()), others
    assert c.tools["weather"] == len(others) - 1


@modes
@pytest.mark.timeout(30)
def test_outer_retry_backoff_does_not_overlap_the_next_call(
    is_sync: bool,
) -> None:
    """
    Unsupported but must stay correct: `ToolRetryMiddleware` replays a
    memoized failure and retries as a new step; the next call waits its turn.
    """

    c, run = Counters(), FakeRun(max_attempts=1)
    retry = ToolRetryMiddleware(
        max_retries=1, initial_delay=0.05, jitter=False, on_failure="continue"
    )
    res, exc, _ = drive(
        run,
        is_sync,
        FAIL_THEN_SLOW,
        failing_and_slow_tools(c),
        c,
        outer=[retry],
    )
    assert exc is None and res is not None
    assert dict(c.tools) == {"fail": 2, "slow": 1}
    assert run.order == [
        "agent/model-0",
        "agent/tool-call_1",
        "agent/tool-call_1:1",
        "agent/tool-call_2",
        "agent/model-1",
    ]


class _ShortCircuitFail(AgentMiddleware[typing.Any, typing.Any, typing.Any]):
    """Answers `fail` calls itself, without calling the handler."""

    def wrap_tool_call(
        self, request: typing.Any, handler: typing.Any
    ) -> typing.Any:
        if request.tool_call["name"] == "fail":
            return ToolMessage("cached", tool_call_id=request.tool_call["id"])
        return handler(request)

    async def awrap_tool_call(
        self, request: typing.Any, handler: typing.Any
    ) -> typing.Any:
        if request.tool_call["name"] == "fail":
            return ToolMessage("cached", tool_call_id=request.tool_call["id"])
        return await handler(request)


@modes
@pytest.mark.timeout(10)
def test_outer_short_circuit_does_not_block_the_next_call(
    is_sync: bool,
) -> None:
    c, run = Counters(), FakeRun()
    res, exc, _ = drive(
        run,
        is_sync,
        FAIL_THEN_SLOW,
        failing_and_slow_tools(c),
        c,
        outer=[_ShortCircuitFail()],
    )
    assert exc is None and res is not None
    assert dict(c.tools) == {"slow": 1}
    assert run.order == ["agent/model-0", "agent/tool-call_2", "agent/model-1"]


@modes
def test_tool_error_handled_by_outer_middleware_does_not_block_next_turn(
    is_sync: bool,
) -> None:
    c, run = Counters(), FakeRun(max_attempts=1)
    script: Script = [
        tool_turn(
            call("local_time", "call_1", city="Paris"),
            call("weather", "call_2", city="Paris"),
        ),
        tool_turn(call("weather", "call_3", city="Tokyo")),
        AIMessage(content="fin"),
    ]
    retry = ToolRetryMiddleware(max_retries=0, on_failure="continue")
    res, exc, _ = drive(
        run,
        is_sync,
        script,
        lambda: make_tools(c, _boom),
        c,
        outer=[retry],
    )
    assert exc is None and res is not None
    assert c.tools["weather"] == 2
    assert res["messages"][-1].content == "fin"


@modes
def test_non_json_tool_artifact_is_not_retried(is_sync: bool) -> None:
    c, run = Counters(), FakeRun(max_attempts=3)

    @tool(response_format="content_and_artifact")
    def blob() -> tuple[str, object]:
        """blob"""
        c.tools["blob"] += 1
        return "ok", object()

    res, exc, _ = drive(
        run, is_sync, [tool_turn(call("blob", "call_1"))], lambda: [blob], c
    )
    assert res is None
    assert isinstance(exc, inngest.NonRetriableError)
    assert "JSON" in str(exc)
    assert c.tools["blob"] == 1
    assert "agent/tool-call_1" not in run.memo


@modes
def test_agents_swapping_order_keep_their_results(is_sync: bool) -> None:
    """
    Without the agent_id prefix both agents would use `model-0`, and the
    second agent would replay the first one's result.
    """

    run = FakeRun()
    results: dict[str, Result] = {}
    for request in range(10):
        first = middleware(run, is_sync, "a")
        mws = {"a": first, "b": same_ctx(first, "b")}
        order = ["a", "b"] if request % 2 == 0 else ["b", "a"]
        try:
            for agent_id in order:
                agent = durable(
                    create_agent(
                        ScriptedModel(
                            script=[AIMessage(content=f"from {agent_id}")],
                            counters=Counters(),
                        ),
                        [],
                        middleware=[mws[agent_id]],
                    )
                )
                results[agent_id] = invoke(agent, mws[agent_id])
            break
        except ResponseInterrupt:
            continue
    assert results["a"]["messages"][-1].content == "from a"
    assert results["b"]["messages"][-1].content == "from b"
    assert sorted(run.order) == ["a/model-0", "b/model-0"]


@modes
def test_sequential_reuse_replays_deterministically(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    script: Script = [*three_calls_script(), *three_calls_script()]
    results: list[Result] = []
    for _ in range(20):
        mw = middleware(run, is_sync)
        agent = durable(
            create_agent(
                ScriptedModel(script=script, counters=c),
                make_tools(c),
                middleware=[mw],
            )
        )
        try:
            results = [invoke(agent, mw), invoke(agent, mw)]
            break
        except ResponseInterrupt:
            continue
    assert len(results) == 2
    assert all(len(e) <= 1 for e in run.executed)
    assert run.order == [
        *EXPECTED,
        "agent/model-2",
        "agent/tool-call_1:1",
        "agent/tool-call_2:1",
        "agent/tool-call_3:1",
        "agent/model-3",
    ]
    assert all(v == 1 for v in run.exec_count.values())
    assert dict(c.tools) == {"local_time": 2, "weather": 4}


@modes
def test_model_fallback_runs_as_the_next_model_step(is_sync: bool) -> None:
    """The fallback runs once the primary's step has used up its retries."""

    c, run = Counters(), FakeRun(max_attempts=2)
    fallback = ScriptedModel(
        script=[AIMessage(content="from fallback")], counters=Counters()
    )
    res, exc, _ = drive(
        run,
        is_sync,
        [RuntimeError("down")],
        list,
        c,
        outer=[ModelFallbackMiddleware(fallback)],
    )
    assert exc is None and res is not None
    assert res["messages"][-1].content == "from fallback"
    assert run.order == ["agent/model-0", "agent/model-1"]
    assert c.model == 2
    # Every request replays the same steps, in the same order.
    final = run.requests[-1]
    assert all(r == final[: len(r)] for r in run.requests)


@modes
def test_tool_call_ids_map_to_distinct_step_ids(is_sync: bool) -> None:
    """
    IDs that would collide with the SDK's `:<n>` suffix for repeated IDs, or
    with each other under naive escaping, still get their own steps.
    """

    c, run = Counters(), FakeRun()
    ids = [["x", "x:1", "a/b"], ["x", "a:b", "a_b", "a%3Ab"]]
    script: Script = [
        *(
            tool_turn(*(call("weather", i, city=i) for i in turn))
            for turn in ids
        ),
        AIMessage(content="fin"),
    ]
    res, exc, _ = drive(run, is_sync, script, lambda: make_tools(c), c)
    assert exc is None and res is not None
    assert c.tools["weather"] == 7
    assert [s for s in run.order if "/tool-" in s] == [
        "agent/tool-x",
        "agent/tool-x%3A1",
        "agent/tool-a%2Fb",
        "agent/tool-x:1",
        "agent/tool-a%3Ab",
        "agent/tool-a_b",
        "agent/tool-a%253Ab",
    ]


@modes
def test_tool_call_without_id_is_rejected(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    script: Script = [tool_turn(call("weather", "", city="Paris"))]
    res, exc, _ = drive(run, is_sync, script, lambda: make_tools(c), c)
    assert res is None
    assert isinstance(exc, inngest.NonRetriableError)
    assert "has no ID" in str(exc)
    assert c.tools["weather"] == 0


# Upstream LangGraph bug, reproducible with LangGraph alone (a Send fan-out
# under max_concurrency=1 whose first task raises). TODO: link the upstream
# issue once it's filed. Strict, so this fails once LangGraph fixes it.
# Replay correctness for the same scenario is asserted by the passing tests.
@pytest.mark.xfail(
    strict=True,
    reason="LangGraph's gated() leaves queued tool coroutines unawaited "
    "when it cancels them",
)
def test_interrupt_with_queued_tool_calls_leaves_no_unawaited_coroutine() -> (
    None
):
    c, run = Counters(), FakeRun()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        drive(run, False, list(three_calls_script()), lambda: make_tools(c), c)
        gc.collect()
    assert [w for w in caught if "never awaited" in str(w.message)] == []


@modes
def test_spans(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    _, exc, _ = drive(
        run, is_sync, list(three_calls_script()), lambda: make_tools(c), c
    )
    assert exc is None
    agent = Span("agent", "Agent", "agent", None)
    assert run.spans["agent/model-0"] == (
        agent,
        Span("agent/model-0", "ScriptedModel", "llm", const.ORIGIN),
    )
    assert run.spans["agent/tool-call_2"] == (
        agent,
        Span("agent/tool-call_2", "weather", "tool", const.ORIGIN),
    )
    assert set(run.spans) == set(EXPECTED)


def test_default_agent_id() -> None:
    mw = InngestMiddleware(context(FakeRun()))
    assert mw._agent_id == "agent"


@modes
def test_invalid_agent_id(is_sync: bool) -> None:
    for agent_id in ["", "a:b"]:
        with pytest.raises(ValueError, match="agent_id"):
            middleware(FakeRun(), is_sync, agent_id)


@modes
def test_duplicate_agent_id(is_sync: bool) -> None:
    mw = middleware(FakeRun(), is_sync)
    with pytest.raises(inngest.NonRetriableError, match="already used"):
        same_ctx(mw, "agent")
    # A new request is a new execution.
    middleware(FakeRun(), is_sync)


def test_wrong_ctx_type() -> None:
    with pytest.raises(TypeError, match="ctx"):
        InngestMiddleware(object(), agent_id="agent")  # type: ignore[arg-type]


@modes
def test_wrong_mode(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    mw = middleware(run, is_sync)
    agent = durable(
        create_agent(
            ScriptedModel(script=[AIMessage(content="fin")], counters=c),
            [],
            middleware=[mw],
        )
    )
    with pytest.raises(inngest.NonRetriableError) as err:
        if is_sync:
            asyncio.run(agent.ainvoke(INPUT))
        else:
            agent.invoke(INPUT)
    expected = "invoke()" if is_sync else "ainvoke()"
    assert f"invoke the agent with {expected}" in str(err.value)
    assert run.order == []


@modes
@pytest.mark.parametrize(
    ("use_durable", "config"),
    [
        pytest.param(False, None, id="not-durable"),
        pytest.param(True, {"max_concurrency": 4}, id="override"),
    ],
)
def test_max_concurrency_other_than_1_is_rejected(
    is_sync: bool, use_durable: bool, config: typing.Any
) -> None:
    c, run = Counters(), FakeRun()
    mw = middleware(run, is_sync)
    agent = create_agent(
        ScriptedModel(script=list(three_calls_script()), counters=c),
        make_tools(c),
        middleware=[mw],
    )
    with pytest.raises(inngest.NonRetriableError, match="max_concurrency=1"):
        invoke(durable(agent) if use_durable else agent, mw, config=config)
    assert run.order == []


def test_durable_rejects_a_checkpointer_before_any_write() -> None:
    saver = InMemorySaver()
    agent = create_agent(
        ScriptedModel(script=[AIMessage(content="fin")], counters=Counters()),
        [],
        middleware=[middleware(FakeRun(), True)],
        checkpointer=saver,
    )
    with pytest.raises(inngest.NonRetriableError, match="checkpointer"):
        durable(agent)
    assert list(saver.list(None)) == []


@modes
@pytest.mark.parametrize("how", ["parent-graph", "config"])
def test_middleware_rejects_an_inherited_checkpointer(
    is_sync: bool, how: str
) -> None:
    c, run = Counters(), FakeRun()
    mw = middleware(run, is_sync)
    agent = durable(
        create_agent(
            ScriptedModel(script=[AIMessage(content="fin")], counters=c),
            [],
            middleware=[mw],
        )
    )
    saver = InMemorySaver()
    config: typing.Any = {"configurable": {"thread_id": "t"}}
    if how == "parent-graph":
        parent = StateGraph(MessagesState)
        parent.add_node("agent", agent)
        parent.add_edge(START, "agent")
        graph: typing.Any = parent.compile(checkpointer=saver).with_config(
            max_concurrency=1
        )
    else:
        graph = agent
        config["configurable"]["__pregel_checkpointer"] = saver
    with pytest.raises(inngest.NonRetriableError, match="checkpointer"):
        invoke(graph, mw, config=config)
    assert run.order == []
    assert c.model == 0


@modes
def test_concurrent_use_of_one_instance(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    mw = middleware(run, is_sync)
    agent = durable(
        create_agent(
            ScriptedModel(
                script=[AIMessage(content="fin")], counters=c, delay=0.05
            ),
            [],
            middleware=[mw],
        )
    )
    errors: list[BaseException] = []
    if is_sync:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(invoke, agent, mw) for _ in "ab"]
        errors = [e for f in futures if (e := f.exception()) is not None]
    else:

        async def both() -> list[object]:
            return list(
                await asyncio.gather(
                    agent.ainvoke(INPUT),
                    agent.ainvoke(INPUT),
                    return_exceptions=True,
                )
            )

        errors = [
            r for r in asyncio.run(both()) if isinstance(r, BaseException)
        ]
    assert sorted(type(e).__name__ for e in errors) == [
        "NonRetriableError",
        "ResponseInterrupt",
    ]
    assert any("invoked concurrently" in str(e) for e in errors)


@modes
def test_subagent_inside_tool_is_rejected(is_sync: bool) -> None:
    c, run = Counters(), FakeRun()
    holder: list[InngestMiddleware] = []

    def subagent() -> typing.Any:
        sub = same_ctx(holder[-1], "sub")
        model = ScriptedModel(script=[AIMessage(content="sub")], counters=c)
        return durable(create_agent(model, [], middleware=[sub]))

    @tool
    def research() -> str:
        """research"""
        return str(subagent().invoke(INPUT)["messages"][-1].content)

    @tool("research")
    async def aresearch() -> str:
        """research"""
        result = await subagent().ainvoke(INPUT)
        return str(result["messages"][-1].content)

    res: Result | None = None
    exc: BaseException | None = None
    for _ in range(5):
        mw = middleware(run, is_sync)
        holder.append(mw)
        agent = durable(
            create_agent(
                ScriptedModel(
                    script=[tool_turn(call("research", "call_1"))], counters=c
                ),
                [research if is_sync else aresearch],
                middleware=[mw],
            )
        )
        try:
            res = invoke(agent, mw)
            break
        except ResponseInterrupt:
            continue
        except BaseException as err:
            exc = err
            break
    assert res is None
    assert isinstance(exc, inngest.NonRetriableError)
    assert "inside another step" in str(exc)
