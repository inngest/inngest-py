"""
Test doubles: replaying fake steps, a scripted chat model, counting tools, and
`drive`, which replays an agent until it finishes.

A `FakeRun` holds what Inngest keeps between requests. Each request builds a
new `FakeStep` or `FakeStepSync` on it, like the SDK builds a new `ctx.step`.
"""

from __future__ import annotations

import asyncio
import collections
import contextvars
import gc
import json
import logging
import time
import typing

import inngest
import pydantic
from inngest._internal import run_context, server_lib, step_lib
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool

from .middleware import InngestMiddleware, durable

Interrupt = step_lib.ResponseInterrupt
Result: typing.TypeAlias = dict[str, typing.Any]
Script: typing.TypeAlias = list[AIMessage | Exception]

INPUT: typing.Any = {"messages": [HumanMessage("hi")]}

# Problems the event loop reported, such as an exception never retrieved.
loop_problems: list[dict[str, object]] = []
_StepToken: typing.TypeAlias = contextvars.Token[step_lib.StepInfo | None]


class FakeRun:
    """
    Memos and counts that outlive a request. A memo hit returns the stored
    JSON as is, like a client without a serializer. A miss runs the body,
    JSON round-trips its output, records it and raises `ResponseInterrupt`.
    Other errors are retried via interrupt until `max_attempts`, then
    memoized as a `StepError`.
    """

    def __init__(self, max_attempts: int = 3) -> None:
        self.memo: dict[str, object] = {}
        self.errors: dict[str, str] = {}
        self.exec_count: collections.Counter[str] = collections.Counter()
        self.attempts: collections.Counter[str] = collections.Counter()
        self.order: list[str] = []
        self.spans: dict[str, tuple[run_context.Span, ...]] = {}
        # Step IDs in the order each request discovered them.
        self.requests: list[list[str]] = []
        # Step IDs each request ran. Inngest runs one new step per request.
        self.executed: list[list[str]] = []
        self.max_attempts = max_attempts


class _FakeStepBase:
    def __init__(self, run: FakeRun) -> None:
        self.run_state = run
        self._counts: collections.Counter[str] = collections.Counter()
        self._discovered: list[str] = []
        self._executed: list[str] = []
        run.requests.append(self._discovered)
        run.executed.append(self._executed)

    def _discover(self, step_id: str) -> str:
        """Suffix a repeated ID like the SDK does, and record its spans."""

        self._counts[step_id] += 1
        count = self._counts[step_id]
        full_id = step_id if count == 1 else f"{step_id}:{count - 1}"
        self._discovered.append(full_id)
        self.run_state.spans[full_id] = run_context.current_span.get()
        error = self.run_state.errors.get(full_id)
        if error is not None:
            raise _step_error(error)
        return full_id

    def _start(self, step_id: str) -> _StepToken:
        self._executed.append(step_id)
        self.run_state.exec_count[step_id] += 1
        if step_id not in self.run_state.order:
            self.run_state.order.append(step_id)
        info = step_lib.StepInfo(
            id=step_id,
            display_name=step_id,
            name=step_id,
            op=server_lib.Opcode.STEP_RUN,
        )
        return run_context.current_step.set(info)

    def _finish(self, step_id: str, out: object) -> typing.NoReturn:
        self.run_state.memo[step_id] = out = json.loads(json.dumps(out))
        raise Interrupt([])

    def _fail(self, step_id: str, err: Exception) -> typing.NoReturn:
        if isinstance(
            err, (inngest.NonRetriableError, inngest.RetryAfterError)
        ):
            raise err
        self.run_state.attempts[step_id] += 1
        if self.run_state.attempts[step_id] >= self.run_state.max_attempts:
            self.run_state.errors[step_id] = f"{type(err).__name__}: {err}"
        raise Interrupt([]) from err


class FakeStep(_FakeStepBase):
    async def run(
        self,
        step_id: str,
        handler: typing.Callable[..., typing.Awaitable[object]],
        *args: object,
    ) -> object:
        full_id = self._discover(step_id)
        if full_id in self.run_state.memo:
            return self.run_state.memo[full_id]
        token = self._start(full_id)
        try:
            out = await handler(*args)
        except Exception as err:
            self._fail(full_id, err)
        finally:
            run_context.current_step.reset(token)
        self._finish(full_id, out)


class FakeStepSync(_FakeStepBase):
    def run(
        self,
        step_id: str,
        handler: typing.Callable[..., object],
        *args: object,
    ) -> object:
        full_id = self._discover(step_id)
        if full_id in self.run_state.memo:
            return self.run_state.memo[full_id]
        token = self._start(full_id)
        try:
            out = handler(*args)
        except Exception as err:
            self._fail(full_id, err)
        finally:
            run_context.current_step.reset(token)
        self._finish(full_id, out)


def _step_error(message: str) -> inngest.StepError:
    name, _, text = message.partition(": ")
    return inngest.StepError(message=text, name=name, stack=None)


def context(run: FakeRun) -> inngest.Context:
    """A real async `Context` for one request, with a fake step."""

    event = inngest.Event(name="test")
    return inngest.Context(
        attempt=0,
        event=event,
        events=[event],
        group=step_lib.Group(),
        job_id=None,
        logger=logging.getLogger("test"),
        request_id=None,
        run_id="run",
        step=typing.cast(step_lib.Step, FakeStep(run)),
    )


def context_sync(run: FakeRun) -> inngest.ContextSync:
    """A real `ContextSync` for one request, with a fake step."""

    event = inngest.Event(name="test")
    return inngest.ContextSync(
        attempt=0,
        event=event,
        events=[event],
        group=step_lib.GroupSync(),
        job_id=None,
        logger=logging.getLogger("test"),
        request_id=None,
        run_id="run",
        step=typing.cast(step_lib.StepSync, FakeStepSync(run)),
    )


class Counters:
    """Tally of model invocations and tool body executions."""

    def __init__(self) -> None:
        self.tools: collections.Counter[str] = collections.Counter()
        self.model = 0


class ScriptedModel(BaseChatModel):
    """
    Chat model replaying `script` in order (the last entry repeats). An
    exception in the script is raised instead. With `by_turn`, the entry is
    picked by the number of model turns in the conversation instead of the
    number of calls so far.
    """

    script: pydantic.SkipValidation[list[AIMessage | Exception]]
    counters: Counters
    # Seconds each call takes, so concurrent invocations overlap.
    delay: float = 0
    by_turn: bool = False

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> ScriptedModel:
        return self

    def _next(self, messages: list[BaseMessage]) -> ChatResult:
        i = self.counters.model
        if self.by_turn:
            i = sum(isinstance(m, AIMessage) for m in messages)
        self.counters.model += 1
        message = self.script[min(i, len(self.script) - 1)]
        if isinstance(message, Exception):
            raise message
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        time.sleep(self.delay)
        return self._next(messages)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        await asyncio.sleep(self.delay)
        return self._next(messages)


def call(name: str, call_id: str, **args: object) -> dict[str, object]:
    """A tool call dict."""

    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def tool_turn(*calls: dict[str, object]) -> AIMessage:
    return AIMessage(content="", tool_calls=calls)


def three_calls_script() -> list[AIMessage]:
    """One turn with three parallel tool calls, then a final answer."""

    return [
        tool_turn(
            call("local_time", "call_1", city="Paris"),
            call("weather", "call_2", city="Paris"),
            call("weather", "call_3", city="Tokyo"),
        ),
        AIMessage(content="All done: greeting."),
    ]


def make_tools(
    counters: Counters,
    local_time_impl: typing.Callable[[str], str] | None = None,
) -> list[BaseTool]:
    """`local_time` and `weather` tools that count their executions."""

    @tool
    def local_time(city: str) -> str:
        """Local time."""
        counters.tools["local_time"] += 1
        return local_time_impl(city) if local_time_impl else f"12:00 in {city}"

    @tool
    def weather(city: str) -> str:
        """Weather."""
        counters.tools["weather"] += 1
        return f"{city}: sunny"

    return [local_time, weather]


def middleware(
    run: FakeRun, is_sync: bool, agent_id: str = "agent"
) -> InngestMiddleware:
    """A new middleware on a new request's context."""

    ctx: inngest.Context | inngest.ContextSync
    ctx = context_sync(run) if is_sync else context(run)
    return InngestMiddleware(ctx, agent_id=agent_id, name="Agent")


def invoke(
    agent: typing.Any,
    mw: InngestMiddleware,
    data: Result = INPUT,
    config: typing.Any = None,
) -> Result:
    if isinstance(mw._ctx, inngest.ContextSync):
        return typing.cast(Result, agent.invoke(data, config))
    return asyncio.run(_ainvoke(agent, data, config))


async def _ainvoke(
    agent: typing.Any, data: Result, config: typing.Any
) -> Result:
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(lambda _, ctx: loop_problems.append(ctx))
    try:
        return typing.cast(Result, await agent.ainvoke(data, config))
    finally:
        gc.collect()
        await asyncio.sleep(0)
        gc.collect()


def drive(
    run: FakeRun,
    is_sync: bool,
    script: Script,
    tools: typing.Callable[[], list[BaseTool]],
    counters: Counters,
    *,
    cap: int = 20,
    outer: list[AgentMiddleware[typing.Any, typing.Any, typing.Any]]
    | None = None,
    data: Result = INPUT,
    **agent_kwargs: typing.Any,
) -> tuple[Result | None, BaseException | None, int]:
    """
    Rebuild the agent and re-invoke until no `ResponseInterrupt` escapes.

    Returns (result | None, escaped exception | None, interrupts).
    """

    interrupts = 0
    for _ in range(cap):
        mw = middleware(run, is_sync)
        agent = durable(
            create_agent(
                ScriptedModel(script=script, counters=counters),
                tools(),
                middleware=[*(outer or []), mw],
                **agent_kwargs,
            )
        )
        try:
            return invoke(agent, mw, data), None, interrupts
        except Interrupt:
            interrupts += 1
        except BaseException as exc:
            return None, exc, interrupts
        finally:
            assert len(run.executed[-1]) <= 1, run.executed[-1]
    raise AssertionError("replay cap hit")
