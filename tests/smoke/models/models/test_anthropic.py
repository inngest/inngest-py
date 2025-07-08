import os
from typing import Any

from inngest.experimental.ai.anthropic import Adapter as AnthropicAdapter
from utils import extract_anthropic_response

# Create Anthropic adapter
anthropic_adapter = AnthropicAdapter(
    auth_key=os.getenv("ANTHROPIC_API_KEY") or "",
    model="claude-3-5-sonnet-latest",
)


def prepare_test_anthropic() -> tuple[AnthropicAdapter, dict[str, Any]]:
    """Prepare the request for the Anthropic adapter test."""
    question = "What is the capital of Texas?"
    body = {
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 1024,
    }
    return (anthropic_adapter, body)


def handle_test_anthropic_response(response: dict[str, Any]) -> dict[str, Any]:
    """Handle the response from the Anthropic adapter test."""
    return {
        "success": True,
        "response": extract_anthropic_response(response),
        "raw_response": str(response),
    }
