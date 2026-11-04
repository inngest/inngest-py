"""
Inngest durability for a LangChain agent, as `create_agent` middleware.

Each model call and each tool call that reaches this middleware becomes a
memoized `step.run`. Inngest replays the function from the top after each
step; LangChain's loop then re-executes, and memoized steps return their
recorded result instead of calling the model or the tool again.

Step IDs are `<agent_id>/model-<n>`, where `n` counts this instance's model
calls, and `<agent_id>/tool-<tool call ID>`. Both are stable across replays:
model calls happen in the same order, and tool call IDs come from memoized
model output.

Inngest runs one new step per request. LangChain runs a turn's tool calls as
parallel tasks, so the agent must run with `max_concurrency=1`, which runs
them one at a time in `tool_calls` order. Once a step ends the request, any
later step of this instance re-raises the same interrupt instead of running.
"""

from __future__ import annotations

import contextlib
import typing
import urllib.parse
import weakref
from typing import Optional

import inngest
from inngest._internal import run_context, step_lib
from langchain.agents import AgentState
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.runnables import RunnableConfig
from langgraph.pregel import Pregel
from langgraph.runtime import Runtime

from . import const, step_output
from .step_output import ToolResult

if not hasattr(step_lib.Group, "_span") or not hasattr(
    step_lib.GroupSync, "_span"
):
    raise ImportError(
        "inngest_langchain needs ctx.group._span, which this version of "
        "inngest doesn't have. Upgrade inngest."
    )

_State: typing.TypeAlias = AgentState[typing.Any]
_Runtime: typing.TypeAlias = Runtime[typing.Any]
_ModelRequest: typing.TypeAlias = ModelRequest[typing.Any]
_ModelResponse: typing.TypeAlias = ModelResponse[typing.Any]
_ModelHandler: typing.TypeAlias = typing.Callable[
    [_ModelRequest], typing.Awaitable[_ModelResponse]
]
_ModelHandlerSync: typing.TypeAlias = typing.Callable[
    [_ModelRequest], _ModelResponse
]
_ToolHandler: typing.TypeAlias = typing.Callable[
    [ToolCallRequest], typing.Awaitable[ToolResult]
]
_ToolHandlerSync: typing.TypeAlias = typing.Callable[
    [ToolCallRequest], ToolResult
]
_Agent = typing.TypeVar(
    "_Agent", bound=Pregel[typing.Any, typing.Any, typing.Any, typing.Any]
)

# LangGraph's config key for the checkpointer in effect, including one
# inherited from a parent graph.
_CHECKPOINTER_KEY = "__pregel_checkpointer"


def durable(agent: _Agent) -> _Agent:
    """
    Prepare a `create_agent` agent for `InngestMiddleware`: run its tool
    calls one at a time, and reject a checkpointer.
    """

    if agent.checkpointer not in (None, False):
        raise inngest.NonRetriableError(_CHECKPOINTER_ERROR)
    return agent.with_config(max_concurrency=1)


class InngestMiddleware(
    AgentMiddleware[AgentState[typing.Any], typing.Any, typing.Any]
):
    """
    Run each model call and tool call as an Inngest step.

    With an async function's `inngest.Context`, invoke the agent with
    `ainvoke`; with a sync function's `inngest.ContextSync`, use `invoke`.
    List it last in `middleware=[...]`, wrap the agent in `durable(...)`, and
    build a new instance for every execution.
    """

    def __init__(
        self,
        ctx: inngest.Context | inngest.ContextSync,
        *,
        agent_id: str = "agent",
        name: str | None = None,
    ) -> None:
        if not isinstance(ctx, (inngest.Context, inngest.ContextSync)):
            raise TypeError(
                "InngestMiddleware needs the Inngest function's ctx, got "
                f"{type(ctx).__name__}"
            )
        _claim_agent_id(ctx.step, agent_id)
        self._ctx = ctx
        self._agent_id = agent_id
        self._agent_span = ctx.group._span(agent_id, name=name, kind="agent")
        self._model_calls = 0
        self._one_at_a_time = _OneAtATime(agent_id)
        # The interrupt that ended this request, once one has.
        self._stopped: BaseException | None = None

    # LangGraph injects `config` when it recognises the annotation. Under
    # postponed annotations it compares strings, and it knows
    # "Optional[RunnableConfig]" but not "RunnableConfig | None".
    def before_agent(
        self,
        state: _State,
        runtime: _Runtime,
        config: Optional[RunnableConfig] = None,  # noqa: UP007
    ) -> dict[str, typing.Any] | None:
        self._sync_ctx()
        _check_config(config)
        return None

    async def abefore_agent(
        self,
        state: _State,
        runtime: _Runtime,
        config: Optional[RunnableConfig] = None,  # noqa: UP007
    ) -> dict[str, typing.Any] | None:
        self._async_ctx()
        _check_config(config)
        return None

    def wrap_model_call(
        self, request: _ModelRequest, handler: _ModelHandlerSync
    ) -> _ModelResponse:
        ctx = self._sync_ctx()
        with self._one_at_a_time():
            step_id = self._model_step_id()
            with self._step(step_id, _model_name(request), "llm"):
                data = ctx.step.run(
                    step_id,
                    lambda: step_output.record_model(request, handler(request)),
                )
        return step_output.replay_model(request, step_id, data)

    async def awrap_model_call(
        self, request: _ModelRequest, handler: _ModelHandler
    ) -> _ModelResponse:
        ctx = self._async_ctx()

        async def call() -> dict[str, object]:
            return step_output.record_model(request, await handler(request))

        with self._one_at_a_time():
            step_id = self._model_step_id()
            with self._step(step_id, _model_name(request), "llm"):
                data = await ctx.step.run(step_id, call)
        return step_output.replay_model(request, step_id, data)

    def wrap_tool_call(
        self, request: ToolCallRequest, handler: _ToolHandlerSync
    ) -> ToolResult:
        ctx = self._sync_ctx()
        name = request.tool_call["name"]
        step_id = self._tool_step_id(request)
        with self._step(step_id, name, "tool"):
            data = ctx.step.run(
                step_id, lambda: step_output.record_tool(name, handler(request))
            )
        return step_output.replay_tool(step_id, data)

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: _ToolHandler
    ) -> ToolResult:
        ctx = self._async_ctx()
        name = request.tool_call["name"]
        step_id = self._tool_step_id(request)

        async def call() -> dict[str, object]:
            return step_output.record_tool(name, await handler(request))

        with self._step(step_id, name, "tool"):
            data = await ctx.step.run(step_id, call)
        return step_output.replay_tool(step_id, data)

    def _model_step_id(self) -> str:
        n = self._model_calls
        self._model_calls += 1
        return f"{self._agent_id}/model-{n}"

    def _tool_step_id(self, request: ToolCallRequest) -> str:
        call_id = request.tool_call["id"]
        if not call_id:
            raise inngest.NonRetriableError(
                f"tool call {request.tool_call['name']} has no ID, so it "
                "can't be recorded as a step"
            )
        # Percent-encoding is reversible, so distinct IDs stay distinct, and
        # it escapes ':', which the SDK uses to suffix repeated step IDs.
        return f"{self._agent_id}/tool-{urllib.parse.quote(call_id, safe='')}"

    @contextlib.contextmanager
    def _step(
        self, step_id: str, name: str, kind: str
    ) -> typing.Iterator[None]:
        if self._stopped is not None:
            raise self._stopped
        _check_not_nested(step_id)
        step_span = self._ctx.group._span(
            step_id, name=name, kind=kind, origin=const.ORIGIN
        )
        try:
            with self._agent_span, step_span:
                yield
        except BaseException as err:
            # An `Exception`, like a memoized `StepError`, is the step's
            # result; anything else ends this request.
            if not isinstance(err, Exception):
                self._stopped = err
            raise

    def _sync_ctx(self) -> inngest.ContextSync:
        if not isinstance(self._ctx, inngest.ContextSync):
            raise inngest.NonRetriableError(
                "InngestMiddleware got an async function's inngest.Context; "
                "invoke the agent with ainvoke(), not invoke()"
            )
        return self._ctx

    def _async_ctx(self) -> inngest.Context:
        if not isinstance(self._ctx, inngest.Context):
            raise inngest.NonRetriableError(
                "InngestMiddleware got a sync function's inngest.ContextSync; "
                "invoke the agent with invoke(), not ainvoke()"
            )
        return self._ctx


_CHECKPOINTER_ERROR = (
    "InngestMiddleware doesn't support LangGraph checkpointers: Inngest "
    "already persists the agent's progress as steps. Remove checkpointer= "
    "from create_agent, from any parent graph and from the invoke config"
)


def _check_config(config: RunnableConfig | None) -> None:
    config = config or {}
    if config.get("configurable", {}).get(_CHECKPOINTER_KEY) is not None:
        raise inngest.NonRetriableError(_CHECKPOINTER_ERROR)
    max_concurrency = config.get("max_concurrency")
    if max_concurrency != 1:
        raise inngest.NonRetriableError(
            "InngestMiddleware needs the agent to run with max_concurrency=1, "
            f"got {max_concurrency}. Wrap the agent with "
            "inngest_langchain.durable(agent) and don't override "
            "max_concurrency when invoking it"
        )


# Agent IDs used so far in each execution. Keyed on ctx.step because Context
# can't be hashed, and every request builds a new step.
_used_agent_ids: weakref.WeakKeyDictionary[object, set[str]] = (
    weakref.WeakKeyDictionary()
)


def _claim_agent_id(step: object, agent_id: str) -> None:
    if not agent_id or ":" in agent_id:
        raise ValueError(
            f"agent_id {agent_id!r} must be non-empty and must not contain ':'"
        )
    used = _used_agent_ids.setdefault(step, set())
    if agent_id in used:
        raise inngest.NonRetriableError(
            f"agent_id {agent_id!r} is already used in this execution; give "
            "each agent a unique agent_id, like f'triage-{i}'"
        )
    used.add(agent_id)


class _OneAtATime:
    """
    Fails when one instance's model calls overlap, i.e. it's invoked
    concurrently. One invocation never overlaps its own model calls.
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._in_flight = 0

    @contextlib.contextmanager
    def __call__(self) -> typing.Iterator[None]:
        self._in_flight += 1
        try:
            if self._in_flight > 1:
                raise inngest.NonRetriableError(
                    f"agent {self._agent_id!r} was invoked concurrently; "
                    "build one middleware instance per invocation"
                )
            yield
        finally:
            self._in_flight -= 1


def _check_not_nested(step_id: str) -> None:
    """Inngest doesn't support steps inside steps."""

    if run_context.current_step.get() is not None:
        raise inngest.NonRetriableError(
            f"step {step_id} would start inside another step; don't run an "
            "agent inside a tool, run it from the function instead"
        )


def _model_name(request: _ModelRequest) -> str:
    model = getattr(request.model, "model", None)
    return str(model or type(request.model).__name__)
