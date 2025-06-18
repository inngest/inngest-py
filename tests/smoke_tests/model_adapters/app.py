import fastapi
import inngest
import inngest.fast_api
from inngest.experimental.ai.openai import Adapter as OpenAIAdapter
from inngest.experimental.ai.anthropic import Adapter as AnthropicAdapter
from inngest.experimental.ai.gemini import Adapter as GeminiAdapter
from inngest.experimental.ai.grok import Adapter as GrokAdapter
from inngest.experimental.ai.deepseek import Adapter as DeepSeekAdapter
import os


inngest_client = inngest.Inngest(app_id="smoke-test-model-adapters-app")

# Create AI adapters
openai_adapter = OpenAIAdapter(
    auth_key=os.getenv("OPENAI_API_KEY"),
    model="o4-mini-2025-04-16",
)

anthropic_adapter = AnthropicAdapter(
    auth_key=os.getenv("ANTHROPIC_API_KEY"),
    model="claude-3-5-sonnet-latest",
)

gemini_adapter = GeminiAdapter(
    auth_key=os.getenv("GEMINI_API_KEY"),
    model="gemini-2.5-pro",
)

grok_adapter = GrokAdapter(
    auth_key=os.getenv("GROK_API_KEY"),
    model="grok-3-latest",
)

deepseek_adapter = DeepSeekAdapter(
    auth_key=os.getenv("DEEPSEEK_API_KEY"),
    model="deepseek-chat",
)

@inngest_client.create_function(
    fn_id="model-adapter-test",
    trigger=inngest.TriggerEvent(event="test-adapters"),
)
async def test_adapters(ctx: inngest.Context) -> dict:
    adapters = {
        "openai": openai_adapter,
        "anthropic": anthropic_adapter,
        "gemini": gemini_adapter,
        "grok": grok_adapter,
        "deepseek": deepseek_adapter,
    }

    # Different state capital questions for each provider
    questions = {
        "openai": "What is the capital of California?",
        "anthropic": "What is the capital of Texas?",
        "gemini": "What is the capital of New York?",
        "grok": "What is the capital of Florida?",
        "deepseek": "What is the capital of Illinois?",
    }

    responses = {}

    for provider_name, adapter in adapters.items():
        try:
            question = questions[provider_name]
            
            # Prepare the request body based on provider
            if provider_name == "gemini":
                # Gemini uses a different format and model should be in URL, not body
                body = {
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": question
                                }
                            ]
                        }
                    ]
                }
            else:
                # Standard OpenAI-style format for other providers
                body = {
                    "messages": [
                        {
                            "role": "user",
                            "content": question
                        }
                    ]
                }

            # Add max_tokens for Anthropic (required parameter)
            if provider_name == "anthropic":
                body["max_tokens"] = 1024

            print(f"Calling {provider_name} with question: {question}")

            ai_response = await ctx.step.ai.infer(
                step_id=f"ai-call-{provider_name}",
                adapter=adapter,
                body=body
            )

            print(f"{provider_name} response: {ai_response}")

            # Extract the text content from the AI response
            # Different providers may have different response formats
            if "choices" in ai_response and len(ai_response["choices"]) > 0:
                # OpenAI/DeepSeek/Grok format
                responses[provider_name] = ai_response["choices"][0]["message"]["content"]
            elif "content" in ai_response and isinstance(ai_response["content"], list):
                # Anthropic format
                responses[provider_name] = ai_response["content"][0]["text"]
            elif "candidates" in ai_response and len(ai_response["candidates"]) > 0:
                # Gemini format
                candidate = ai_response["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    responses[provider_name] = candidate["content"]["parts"][0]["text"]
                else:
                    responses[provider_name] = str(candidate)
            else:
                # Fallback for unknown format
                responses[provider_name] = str(ai_response)

        except Exception as e:
            print(f"Error with {provider_name}: {str(e)}")
            responses[provider_name] = f"Error: {str(e)}"

    return responses

app = fastapi.FastAPI()

inngest.fast_api.serve(
    app,
    inngest_client,
    [test_adapters],
)