import os
from typing import Any, Callable, TypedDict

import fastapi
import inngest
import inngest.fast_api
from inngest._internal import types
from inngest.experimental.ai.anthropic import Adapter as AnthropicAdapter
from inngest.experimental.ai.base import BaseAdapter
from inngest.experimental.ai.deepseek import Adapter as DeepSeekAdapter
from inngest.experimental.ai.gemini import Adapter as GeminiAdapter
from inngest.experimental.ai.grok import Adapter as GrokAdapter
from inngest.experimental.ai.openai import Adapter as OpenAIAdapter


class ProviderConfig(TypedDict):
    adapter: BaseAdapter
    parser: Callable[[dict[str, Any]], str]


inngest_client = inngest.Inngest(app_id="smoke-test-model-adapters-app")

# Create AI adapters
openai_adapter = OpenAIAdapter(
    auth_key=os.getenv("OPENAI_API_KEY") or "",
    model="o4-mini-2025-04-16",
)

anthropic_adapter = AnthropicAdapter(
    auth_key=os.getenv("ANTHROPIC_API_KEY") or "",
    model="claude-3-5-sonnet-latest",
)

gemini_adapter = GeminiAdapter(
    auth_key=os.getenv("GEMINI_API_KEY") or "",
    model="gemini-2.5-pro",
)

grok_adapter = GrokAdapter(
    auth_key=os.getenv("GROK_API_KEY") or "",
    model="grok-3-latest",
)

deepseek_adapter = DeepSeekAdapter(
    auth_key=os.getenv("DEEPSEEK_API_KEY") or "",
    model="deepseek-chat",
)


def extract_openai_response(response: dict[str, Any]) -> str:
    """Extract text from OpenAI/DeepSeek/Grok format response."""
    choices = response.get("choices", [])
    if not choices or not types.is_list(choices):
        return str(response)

    choice = choices[0]
    if not types.is_dict(choice):
        return str(choice)

    message = choice.get("message", {})
    if types.is_dict(message):
        return str(message.get("content", ""))

    return str(choice)


def extract_anthropic_response(response: dict[str, Any]) -> str:
    """Extract text from Anthropic format response."""
    content = response.get("content", [])
    if not content or not types.is_list(content):
        return str(response)

    if len(content) > 0 and types.is_dict(content[0]):
        return str(content[0].get("text", ""))

    return str(content)


def extract_gemini_response(response: dict[str, Any]) -> str:
    """Extract text from Gemini format response."""
    candidates = response.get("candidates", [])
    if not candidates or not types.is_list(candidates) or len(candidates) == 0:
        return str(response)

    candidate = candidates[0]
    if not types.is_dict(candidate):
        return str(candidate)

    content = candidate.get("content", {})
    if not types.is_dict(content):
        return str(candidate)

    parts = content.get("parts", [])
    if types.is_list(parts) and len(parts) > 0 and types.is_dict(parts[0]):
        return str(parts[0].get("text", ""))

    return str(candidate)


@inngest_client.create_function(
    fn_id="model-adapter-test",
    trigger=inngest.TriggerEvent(event="test-adapters"),
)
async def test_adapters(ctx: inngest.Context) -> dict[str, str]:
    # Map each provider to its adapter and parser
    provider_config: dict[str, ProviderConfig] = {
        "openai": {
            "adapter": openai_adapter,
            "parser": extract_openai_response,
        },
        "anthropic": {
            "adapter": anthropic_adapter,
            "parser": extract_anthropic_response,
        },
        "gemini": {
            "adapter": gemini_adapter,
            "parser": extract_gemini_response,
        },
        "grok": {
            "adapter": grok_adapter,
            "parser": extract_openai_response,  # Uses OpenAI format
        },
        "deepseek": {
            "adapter": deepseek_adapter,
            "parser": extract_openai_response,  # Uses OpenAI format
        },
    }

    # Different state capital questions for each provider
    questions = {
        "openai": "What is the capital of California?",
        "anthropic": "What is the capital of Texas?",
        "gemini": "What is the capital of New York?",
        "grok": "What is the capital of Florida?",
        "deepseek": "What is the capital of Illinois?",
    }

    responses: dict[str, str] = {}

    for provider_name, config in provider_config.items():
        try:
            question = questions[provider_name]
            adapter = config["adapter"]
            parser = config["parser"]

            # Prepare the request body based on provider
            if provider_name == "gemini":
                # Gemini uses a different format
                body: dict[str, Any] = {
                    "contents": [{"parts": [{"text": question}]}]
                }
            else:
                # Standard OpenAI-style format for other providers
                body = {"messages": [{"role": "user", "content": question}]}

            # Add max_tokens for Anthropic (required parameter)
            if provider_name == "anthropic":
                body["max_tokens"] = 1024

            print(f"Calling {provider_name} with question: {question}")

            ai_response = await ctx.step.ai.infer(
                step_id=f"ai-call-{provider_name}", adapter=adapter, body=body
            )

            print(f"{provider_name} response: {ai_response}")

            # Use the specific parser for this provider
            responses[provider_name] = parser(ai_response)

        except Exception as e:
            print(f"Error with {provider_name}: {e!s}")
            responses[provider_name] = f"Error: {e!s}"

    return responses


app = fastapi.FastAPI()

inngest.fast_api.serve(
    app,
    inngest_client,
    [test_adapters],
)
