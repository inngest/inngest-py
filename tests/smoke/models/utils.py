from typing import Any

from inngest._internal import types


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


def extract_gemini_thinking_response(response: dict[str, Any]) -> str:
    """Extract text from Gemini format response, separating thoughts from final answer."""
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
    if not types.is_list(parts):
        return str(candidate)

    thoughts = []
    final_answers = []

    for part in parts:
        if types.is_dict(part) and "text" in part:
            text = str(part.get("text", ""))
            if part.get("thought", False):
                thoughts.append(f"🧠 Reasoning: {text}")
            else:
                final_answers.append(f"💡 Answer: {text}")

    result_parts = []
    if thoughts:
        result_parts.append("\n".join(thoughts))
    if final_answers:
        result_parts.append("\n".join(final_answers))

    return "\n\n".join(result_parts) if result_parts else str(candidate)
