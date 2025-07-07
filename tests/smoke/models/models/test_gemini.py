import os
from typing import Any

from inngest.experimental.ai.gemini import (
    Adapter as GeminiAdapter,
)
from inngest.experimental.ai.gemini import (
    GenerationConfig,
    ThinkingConfig,
)
from utils import extract_gemini_response, extract_gemini_thinking_response

# Create Gemini adapters
gemini_adapter = GeminiAdapter(
    auth_key=os.getenv("GEMINI_API_KEY") or "",
    model="gemini-2.0-flash-exp",
)

gemini_enhanced_adapter = GeminiAdapter(
    auth_key=os.getenv("GEMINI_API_KEY") or "",
    model="gemini-2.0-flash-thinking-exp",
    generation_config=GenerationConfig(
        temperature=0.7,
        max_output_tokens=2048,
        thinking_config=ThinkingConfig(
            thinking_budget=1024, include_thoughts=True
        ),
    ),
)

gemini_structured_adapter = GeminiAdapter(
    auth_key=os.getenv("GEMINI_API_KEY") or "",
    model="gemini-2.0-flash-exp",
    generation_config=GenerationConfig(
        temperature=0.3,
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {
                "capital": {"type": "string"},
                "state": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
            },
            "required": ["capital", "state", "confidence"],
        },
    ),
)


# Basic Test
def prepare_gemini_basic_test() -> tuple[GeminiAdapter, dict[str, Any]]:
    question = "Say hello and explain what you are in one sentence."
    body = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 100},
    }
    return (gemini_adapter, body)


def handle_gemini_basic_test(response: dict[str, Any]) -> dict[str, str]:
    return {
        "success": True,
        "response": extract_gemini_response(response),
        "raw_response": str(response),
    }


# Enhanced Tests
def prepare_gemini_pure_thinking_test() -> tuple[GeminiAdapter, dict[str, Any]]:
    question = "Think through this step by step: If I have 15 apples and give away 7, then buy 12 more, how many do I have? Show your reasoning process."
    body = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 300,
            "thinkingConfig": {"thinkingBudget": 1024, "includeThoughts": True},
        },
    }
    return (gemini_enhanced_adapter, body)


def prepare_gemini_mixed_thinking_test() -> tuple[
    GeminiAdapter, dict[str, Any]
]:
    question = "Calculate 15 - 7 + 12. Think about it first, then give me the final answer clearly."
    body = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 400,
            "thinkingConfig": {"thinkingBudget": 512, "includeThoughts": True},
        },
    }
    return (gemini_enhanced_adapter, body)


def prepare_gemini_workflow_test() -> tuple[GeminiAdapter, dict[str, Any]]:
    question = "What's 8 + 12? Think through it step by step, then give me just the number."
    body = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 500,
            "thinkingConfig": {"thinkingBudget": 300, "includeThoughts": True},
        },
    }
    return (gemini_enhanced_adapter, body)


def handle_gemini_thinking_response(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "response": extract_gemini_thinking_response(response),
        "raw_response": response,
    }


def prepare_gemini_structured_test() -> tuple[GeminiAdapter, dict[str, Any]]:
    question = (
        "Generate a fictional person profile with name, age, and hobbies."
    )
    body = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 200,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "number"},
                    "hobbies": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "age", "hobbies"],
            },
        },
    }
    return (gemini_structured_adapter, body)


def handle_gemini_structured_response(
    response: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": True,
        "response": extract_gemini_response(response),
        "raw_response": response,
    }


def prepare_gemini_stop_sequences_test() -> tuple[
    GeminiAdapter, dict[str, Any]
]:
    question = "Count from 1 to 10, but write STOP after 5."
    body = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 500,
            "stopSequences": ["STOP"],
        },
    }
    return (gemini_adapter, body)


def handle_gemini_stop_sequences_response(
    response: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": True,
        "response": extract_gemini_response(response),
        "raw_response": response,
    }


def prepare_gemini_conversion_test() -> tuple[GeminiAdapter, dict[str, Any]]:
    adapter = GeminiAdapter(
        auth_key=os.getenv("GEMINI_API_KEY") or "", model="gemini-2.0-flash-exp"
    )
    body = {
        "messages": [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"},
            {"role": "user", "content": "What's 5 + 3?"},
        ]
    }
    return (adapter, body)


def handle_gemini_conversion_response(
    response: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": True,
        "response": extract_gemini_response(response),
        "raw_response": response,
    }


# Error Handling Test
def prepare_gemini_error_handling_test() -> tuple[
    GeminiAdapter, dict[str, Any]
]:
    adapter = GeminiAdapter(
        auth_key="invalid-key-for-testing", model="gemini-2.0-flash-exp"
    )
    body = {
        "contents": [{"parts": [{"text": "Hello"}]}],
        "generationConfig": {"maxOutputTokens": 10},
    }
    return (adapter, body)


def handle_gemini_error_handling_response(
    response: dict[str, Any],
) -> dict[str, Any]:
    # This should not be called if an error is thrown, but is here for completeness
    return {
        "success": False,
        "error": "Expected error not thrown",
        "unexpected_response": str(response),
    }
