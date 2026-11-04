# Inngest LangChain

Durable [LangChain](https://docs.langchain.com/oss/python/langchain/overview) agents for the [Inngest Python SDK](https://github.com/inngest/inngest-py). `InngestMiddleware` runs each model call and each tool call that reaches it as an Inngest step. When a run fails or is interrupted, Inngest retries it from the top, and calls that already finished return their recorded result instead of running again.

> **Experimental:** this package depends on `ctx.group._span`, an experimental and private SDK API. It can change in any `inngest` release. The package checks for it on import and raises an `ImportError` if it's missing.

## Installation

```sh
pip install inngest_langchain
```

## Quickstart

```py
import inngest
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool

from inngest_langchain import InngestMiddleware, durable

client = inngest.Inngest(app_id="my_app")
model = init_chat_model("anthropic:claude-sonnet-5-5")  # pip install langchain-anthropic


@tool
def weather(city: str) -> str:
    """Current weather in a city."""
    return f"{city}: sunny"


@client.create_function(
    fn_id="research",
    retries=3,  # Inngest owns retries
    trigger=inngest.TriggerEvent(event="app/research"),
)
async def research(ctx: inngest.Context) -> str:
    agent = durable(
        create_agent(
            model,
            [weather],
            middleware=[InngestMiddleware(ctx, name="Research agent")],
        )
    )
    result = await agent.ainvoke({"messages": [("user", "Weather in Paris?")]})
    return result["messages"][-1].text
```

If the `weather` tool raises, Inngest retries the run. The model's tool call is a recorded step, so the retry doesn't call the model again: it replays the model's answer and runs only `weather`.

In a sync function, take `inngest.ContextSync` and call `agent.invoke(...)`. The same class handles both; calling the other mode's method fails with a `NonRetriableError`.

## Rules

- **Wrap the agent in `durable(...)`.** It runs the agent with `max_concurrency=1`, so a turn's parallel tool calls run one at a time, in `tool_calls` order: Inngest runs one new step per request. Don't override `max_concurrency` when invoking.
- **No checkpointers.** Inngest already persists the agent's progress. `durable` rejects an agent compiled with a checkpointer before anything is written. A checkpointer inherited from a parent graph or passed in the invoke config is caught when the agent starts, after LangGraph has written its first checkpoint.
- **Inngest owns retries.** Don't use `ModelRetryMiddleware` or `ToolRetryMiddleware`; set the function's `retries=` instead. Their backoff sleeps would run again on every replay, and each retry becomes another step.
- **`ModelFallbackMiddleware` works.** The fallback model runs as the next model step, but only after Inngest has used up the primary step's retries, so each turn that falls back pays for all of the primary's failed attempts.
- **List the middleware last** in `middleware=[...]`, so it's the innermost wrapper.
- **Other middleware hooks run again on every replay.** Only model and tool calls are recorded. Hooks such as `before_model` and `wrap_model_call` of other middleware must be deterministic and free of side effects. `SummarizationMiddleware` isn't supported: its summary is a model call outside any step.
- **Build a new instance per execution**, inside the function. Don't invoke one instance concurrently.
- **`agent_id` is unique per execution.** It defaults to `"agent"`. For several agents use something like `agent_id=f"triage-{i}"`. It can't be empty or contain `:`.
- **No subagents inside tools.** Inngest doesn't support steps inside steps. Run subagents from the function instead.
- **Run agents concurrently with `ctx.group.parallel`.** `asyncio.gather` gives correct results, but two agents can start a step in the same request, and the one Inngest doesn't record runs again.

## Known issues

- **Async: `RuntimeWarning: coroutine 'arun_with_retry' was never awaited`.** When a request ends while parallel tool calls are still queued behind `max_concurrency=1`, LangGraph cancels the queued calls before they start and Python warns about their unstarted coroutines. It's harmless: those calls run on a later request. This is a LangGraph bug (upstream issue to be filed).

## What's recorded

- A model step records that call's output: the new messages and any structured response, not the whole conversation.
- A tool step records what the tool call returned after the tool's wrapping: a `ToolMessage`, or a `Command(update=...)` without routing (`goto`, `graph` or `resume`). Tools that return plain values such as a `str` are fine; LangChain wraps them in a `ToolMessage`.
- A structured response is stored as JSON and rebuilt with the same schema on replay. A response that wouldn't come back identical, for example because of a non-idempotent validator or an enum in an `Any` field, fails when recorded.
- Other values that aren't JSON, such as a `datetime` in a `ToolMessage` artifact, come back as their JSON form on replay. Values that can't be serialized at all fail the run.
- Inngest allows 4MB per step output and 32MB of total run state.

## Step IDs and spans

- Model calls: `<agent_id>/model-<n>`, counting this instance's model calls.
- Tool calls: `<agent_id>/tool-<tool call ID>`, with the ID percent-encoded so `:` and `/` can't collide with other steps.
- Every step is grouped under one span per agent in the run's trace, named by `name` (defaults to `agent_id`).
