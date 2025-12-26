from __future__ import annotations

import asyncio
import contextlib
import datetime
import functools
import typing
from collections.abc import Iterator, Sequence
from typing import Any, overload

import httpx
import pydantic
from pydantic_ai import AbstractToolset, models
from pydantic_ai import (
    messages as _messages,
)
from pydantic_ai import (
    usage as _usage,
)
from pydantic_ai.agent import (
    AbstractAgent,
    AgentRunResult,
    EventStreamHandler,
    WrapperAgent,
)
from pydantic_ai.agent.abstract import RunOutputDataT
from pydantic_ai.builtin_tools import AbstractBuiltinTool
from pydantic_ai.messages import ModelResponse
from pydantic_ai.output import OutputDataT, OutputSpec
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import AgentDepsT, DeferredToolResults
from pydantic_ai.toolsets import FunctionToolset
from typing_extensions import Never

import inngest
from inngest.experimental import get_step_context


class EventRuns(pydantic.BaseModel):
    data: list[Run]


class Run(pydantic.BaseModel):
    output: dict[str, typing.Any]
    status: str


class InngestAgent(WrapperAgent[AgentDepsT, OutputDataT]):
    def __init__(
        self,
        inngest_client: inngest.Inngest,
        wrapped: AbstractAgent[AgentDepsT, OutputDataT],
    ):
        super().__init__(wrapped)

        original_request = self.model.request  # type: ignore[union-attr]

        def request(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            step = get_step_context()
            return step.run(
                "llm-request",
                functools.partial(original_request, *args, **kwargs),
                output_type=ModelResponse,
            )

        self.model.request = request  # type: ignore[method-assign,union-attr]

        self._inngest_client = inngest_client
        agent_name = wrapped.name or "default"
        self._event_name = f"agent/{agent_name}"

        self._toolsets = [
            toolset.visit_and_replace(stepify_toolset)
            for toolset in wrapped.toolsets
        ]

        @inngest_client.create_function(
            fn_id=agent_name,
            trigger=inngest.TriggerEvent(event=self._event_name),
            output_type=AgentRunResult,
        )
        async def fn(ctx: inngest.Context) -> AgentRunResult:
            try:
                return await self.wrapped.run(**ctx.event.data)  # type: ignore
            except BaseException as e:
                err = e.args[1][0]
                raise err

        self.fn = fn

    @property
    def toolsets(self) -> Sequence[AbstractToolset[AgentDepsT]]:
        with self._inngest_overrides():
            return super().toolsets

    @contextlib.contextmanager
    def _inngest_overrides(self) -> Iterator[None]:
        with super().override(
            model=self.wrapped.model,  # type: ignore[arg-type]
            toolsets=self._toolsets,
            tools=[],
        ):
            yield

    @overload
    async def run(
        self,
        user_prompt: str | Sequence[_messages.UserContent] | None = None,
        *,
        output_type: None = None,
        message_history: Sequence[_messages.ModelMessage] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
        model: models.Model | models.KnownModelName | str | None = None,
        deps: AgentDepsT = None,  # type: ignore[assignment]
        model_settings: ModelSettings | None = None,
        usage_limits: _usage.UsageLimits | None = None,
        usage: _usage.RunUsage | None = None,
        infer_name: bool = True,
        toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
        builtin_tools: Sequence[AbstractBuiltinTool] | None = None,
        event_stream_handler: EventStreamHandler[AgentDepsT] | None = None,
    ) -> AgentRunResult[OutputDataT]: ...

    @overload
    async def run(
        self,
        user_prompt: str | Sequence[_messages.UserContent] | None = None,
        *,
        output_type: OutputSpec[RunOutputDataT],
        message_history: Sequence[_messages.ModelMessage] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
        model: models.Model | models.KnownModelName | str | None = None,
        deps: AgentDepsT = None,  # type: ignore[assignment]
        model_settings: ModelSettings | None = None,
        usage_limits: _usage.UsageLimits | None = None,
        usage: _usage.RunUsage | None = None,
        infer_name: bool = True,
        toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
        builtin_tools: Sequence[AbstractBuiltinTool] | None = None,
        event_stream_handler: EventStreamHandler[AgentDepsT] | None = None,
    ) -> AgentRunResult[RunOutputDataT]: ...

    async def run(
        self,
        user_prompt: str | Sequence[_messages.UserContent] | None = None,
        *,
        output_type: OutputSpec[RunOutputDataT] | None = None,
        message_history: Sequence[_messages.ModelMessage] | None = None,
        deferred_tool_results: DeferredToolResults | None = None,
        model: models.Model | models.KnownModelName | str | None = None,
        deps: AgentDepsT = None,  # type: ignore[assignment]
        model_settings: ModelSettings | None = None,
        usage_limits: _usage.UsageLimits | None = None,
        usage: _usage.RunUsage | None = None,
        infer_name: bool = True,
        toolsets: Sequence[AbstractToolset[AgentDepsT]] | None = None,
        builtin_tools: Sequence[AbstractBuiltinTool] | None = None,
        event_stream_handler: EventStreamHandler[AgentDepsT] | None = None,
        **_deprecated_kwargs: Never,
    ) -> AgentRunResult[Any]:
        kwargs = {
            k: v
            for k, v in locals().items()
            if k not in ["_deprecated_kwargs", "self"] and v is not None
        }

        event_ids = await self._inngest_client.send(
            inngest.Event(
                data=kwargs,
                name=self._event_name,
            )
        )
        event_id = event_ids[0]

        # TODO: Make these configurable
        max_duration = datetime.timedelta(minutes=5)
        poll_interval = datetime.timedelta(seconds=2)

        poll_start_time = datetime.datetime.now()
        async with httpx.AsyncClient() as client:
            attempt = 0
            while datetime.datetime.now() - poll_start_time < max_duration:
                attempt += 1
                if attempt > 1:
                    await asyncio.sleep(poll_interval.total_seconds())

                response = await client.get(
                    f"{self._inngest_client.api_origin}/v1/events/{event_id}/runs"
                )
                if response.status_code == 200:
                    try:
                        data = EventRuns.model_validate_json(response.text)
                    except pydantic.ValidationError:
                        continue

                    if len(data.data) != 1:
                        continue

                    run = data.data[0]
                    if run.status != "Completed":
                        continue

                    return AgentRunResult(**run.output)

        raise Exception("failed to get run output")


def stepify_toolset(
    toolset: AbstractToolset[typing.Any],
) -> AbstractToolset[typing.Any]:
    if isinstance(toolset, FunctionToolset):
        original_call_tool = toolset.call_tool

        def wrapped(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            tool_name = args[0]
            step = get_step_context()
            return step.run(
                tool_name,
                functools.partial(original_call_tool, *args, **kwargs),
            )

        toolset.call_tool = wrapped  # type: ignore[method-assign]

    return toolset
