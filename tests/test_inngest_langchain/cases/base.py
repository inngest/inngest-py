import collections
import dataclasses
import json
import typing

import inngest
import pydantic
import test_core
from inngest._internal import server_lib
from inngest_langchain import InngestMiddleware, durable
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool, tool
from test_core import base

BaseState = base.BaseState
create_test_name = base.create_test_name

INPUT: typing.Any = {"messages": [HumanMessage("What's the weather?")]}


class TestClass(typing.Protocol):
    client: inngest.Inngest


@dataclasses.dataclass
class Case:
    fn: inngest.Function[typing.Any]
    name: str
    run_test: typing.Callable[[TestClass], typing.Awaitable[None]]


def create_event_name(framework: server_lib.Framework, test_name: str) -> str:
    return test_core.worker_suffix(f"{framework.value}/{test_name}")


class ScriptedModel(BaseChatModel):
    """
    Chat model that needs no API key. Answers with script[n], where n is the
    number of model turns so far, so replays see the same answers.
    """

    script: pydantic.SkipValidation[list[AIMessage]]

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> "ScriptedModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object = None,
        **kwargs: object,
    ) -> ChatResult:
        turn = sum(isinstance(m, AIMessage) for m in messages)
        return ChatResult(
            generations=[ChatGeneration(message=self.script[turn])]
        )


def call(name: str, call_id: str, **args: object) -> dict[str, object]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def tool_turn(*calls: dict[str, object]) -> AIMessage:
    return AIMessage(content="", tool_calls=calls)


def weather_tools(counts: collections.Counter[str]) -> list[BaseTool]:
    """Tools that count how often their bodies run."""

    @tool
    def weather(city: str) -> str:
        """Weather."""
        counts["weather"] += 1
        return f"{city}: sunny"

    @tool
    def local_time(city: str) -> str:
        """Local time."""
        counts["local_time"] += 1
        return f"12:00 in {city}"

    return [weather, local_time]


class _State(BaseState):
    pass


def agent_case(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
    *,
    test_name: str,
    script: list[AIMessage],
    steps: list[str],
    tools: list[str],
) -> Case:
    """
    A function that runs one durable agent. The test checks that it completes
    with the script's answer, that every step ran, and that each tool in
    `tools` ran once.
    """

    event_name = create_event_name(framework, test_name)
    state = _State()
    counts: collections.Counter[str] = collections.Counter()

    def agent(ctx: inngest.Context | inngest.ContextSync) -> typing.Any:
        mw = InngestMiddleware(ctx, agent_id="weather", name="Weather agent")
        return durable(
            create_agent(
                ScriptedModel(script=script),
                weather_tools(counts),
                middleware=[mw],
            )
        )

    @client.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> str:
        state.run_id = ctx.run_id
        result = agent(ctx).invoke(INPUT)
        return str(result["messages"][-1].content)

    @client.create_function(
        fn_id=test_name,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> str:
        state.run_id = ctx.run_id
        result = await agent(ctx).ainvoke(INPUT)
        return str(result["messages"][-1].content)

    async def run_test(self: TestClass) -> None:
        self.client.send_sync(inngest.Event(name=event_name))

        run_id = await state.wait_for_run_id()
        run = await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )
        assert run.output is not None
        assert json.loads(run.output) == script[-1].content

        for step_id in steps:
            output = json.loads(
                await test_core.helper.client.get_step_output(
                    run_id=run_id,
                    step_id=step_id,
                )
            )
            assert test_core.get_nested(output, "data.v") == 1

        assert counts == collections.Counter(tools)

    fn: inngest.Function[typing.Any] = fn_sync if is_sync else fn_async
    return Case(fn=fn, run_test=run_test, name=test_name)
