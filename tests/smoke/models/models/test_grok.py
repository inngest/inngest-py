import os
from typing import Any

import inngest
from inngest.experimental.ai.grok import Adapter as GrokAdapter
from utils import extract_openai_response

# Create Grok adapter
grok_adapter = GrokAdapter(
    auth_key=os.getenv("GROK_API_KEY") or "",
    model="grok-3-latest",
)

def prepare_test_grok() -> tuple[GrokAdapter, dict[str, Any]]:
    """Prepare the request for the Grok adapter test."""
    question = "What is the capital of Florida?"
    body = {"messages": [{"role": "user", "content": question}]}
    return (grok_adapter, body)

def handle_test_grok_response(response: dict[str, Any]) -> dict[str, str]:
    """Handle the response from the Grok adapter test."""
    return {
        "success": True,
        "response": extract_openai_response(response),
        "raw_response": str(response)
    } 