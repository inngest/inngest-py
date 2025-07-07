import os
from typing import Any

from inngest.experimental.ai.openai import Adapter as OpenAIAdapter
from utils import extract_openai_response

# Create OpenAI adapter
openai_adapter = OpenAIAdapter(
    auth_key=os.getenv("OPENAI_API_KEY") or "",
    model="o4-mini-2025-04-16",
)


def prepare_test_openai() -> tuple[OpenAIAdapter, dict[str, Any]]:
    """Prepare the request for the OpenAI adapter test."""
    question = "What is the capital of California?"
    body = {"messages": [{"role": "user", "content": question}]}
    return (openai_adapter, body)


def handle_test_openai_response(response: dict[str, Any]) -> dict[str, str]:
    """Handle the response from the OpenAI adapter test."""
    return {
        "success": True,
        "response": extract_openai_response(response),
        "raw_response": str(response),
    }
