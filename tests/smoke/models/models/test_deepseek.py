import os
from typing import Any

from inngest.experimental.ai.deepseek import Adapter as DeepSeekAdapter
from utils import extract_openai_response

# Create DeepSeek adapter
deepseek_adapter = DeepSeekAdapter(
    auth_key=os.getenv("DEEPSEEK_API_KEY") or "",
    model="deepseek-chat",
)


def prepare_test_deepseek() -> tuple[DeepSeekAdapter, dict[str, Any]]:
    """Prepare the request for the DeepSeek adapter test."""
    question = "What is the capital of Illinois?"
    body = {"messages": [{"role": "user", "content": question}]}
    return (deepseek_adapter, body)


def handle_test_deepseek_response(response: dict[str, Any]) -> dict[str, str]:
    """Handle the response from the DeepSeek adapter test."""
    return {
        "success": True,
        "response": extract_openai_response(response),
        "raw_response": str(response),
    }
