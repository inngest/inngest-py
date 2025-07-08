from __future__ import annotations

import logging
from typing import Any, Optional

from .base import BaseAdapter

# Set up logging
logger = logging.getLogger(__name__)


class ThinkingConfig:
    """
    Configuration for the 'thinking' feature in Gemini models.

    This allows the model to output its reasoning process (thoughts) before
    providing the final answer.
    """

    def __init__(
        self,
        *,
        thinking_budget: Optional[int] = None,
        include_thoughts: Optional[bool] = None,
    ) -> None:
        """
        Args:
            thinking_budget: The token budget allocated for thinking.
            include_thoughts: Whether to include the thinking process in the output.
        """
        self.thinking_budget = thinking_budget
        self.include_thoughts = include_thoughts

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        result: dict[str, Any] = {}
        if self.thinking_budget is not None:
            result["thinkingBudget"] = self.thinking_budget
        if self.include_thoughts is not None:
            result["includeThoughts"] = self.include_thoughts
        return result


class GenerationConfig:
    r"""
    Configuration options for model generation and outputs.

    Use this class to control how Gemini generates responses, from basic parameters
    like temperature and token limits to advanced features like thinking, structured output,
    and multimodal responses.

    **Example Basic Usage:**
    ```python
    config = GenerationConfig(
        temperature=0.7,
        max_output_tokens=1000,
        stop_sequences=["\n\n"]
    )
    ```

    **Example Structured JSON Output:**
    ```python
    config = GenerationConfig(
        response_mime_type="application/json",
        response_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"}
            }
        }
    )
    ```

    **Example Thinking Mode:**
    ```python
    config = GenerationConfig(
        thinking_config=ThinkingConfig(
            thinking_budget=2048,  # Higher budget for complex tasks
            include_thoughts=True   # Get reasoning insights
        )
    )
    ```
    """

    def __init__(
        self,
        *,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
        stop_sequences: Optional[list[str]] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[dict[str, Any]] = None,
        response_json_schema: Optional[Any] = None,
        response_modalities: Optional[list[str]] = None,
        candidate_count: Optional[int] = None,
        seed: Optional[int] = None,
        logprobs: Optional[int] = None,
        enable_enhanced_civic_answers: Optional[bool] = None,
        speech_config: Optional[dict[str, Any]] = None,
        thinking_config: Optional[ThinkingConfig] = None,
        media_resolution: Optional[str] = None,
    ) -> None:
        """Initializes the GenerationConfig."""
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.max_output_tokens = max_output_tokens
        self.stop_sequences = stop_sequences
        self.presence_penalty = presence_penalty
        self.frequency_penalty = frequency_penalty
        self.response_mime_type = response_mime_type
        self.response_schema = response_schema
        self.response_json_schema = response_json_schema
        self.response_modalities = response_modalities
        self.candidate_count = candidate_count
        self.seed = seed
        self.logprobs = logprobs
        self.enable_enhanced_civic_answers = enable_enhanced_civic_answers
        self.speech_config = speech_config
        self.thinking_config = thinking_config
        self.media_resolution = media_resolution

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API request."""
        result: dict[str, Any] = {}
        if self.temperature is not None:
            result["temperature"] = self.temperature
        if self.top_p is not None:
            result["topP"] = self.top_p
        if self.top_k is not None:
            result["topK"] = self.top_k
        if self.max_output_tokens is not None:
            result["maxOutputTokens"] = self.max_output_tokens
        if self.stop_sequences is not None:
            result["stopSequences"] = self.stop_sequences
        if self.presence_penalty is not None:
            result["presencePenalty"] = self.presence_penalty
        if self.frequency_penalty is not None:
            result["frequencyPenalty"] = self.frequency_penalty
        if self.response_mime_type is not None:
            result["responseMimeType"] = self.response_mime_type
        if self.response_schema is not None:
            result["responseSchema"] = self.response_schema
        if self.response_json_schema is not None:
            result["response_json_schema"] = self.response_json_schema
        if self.response_modalities is not None:
            result["responseModalities"] = self.response_modalities
        if self.candidate_count is not None:
            result["candidateCount"] = self.candidate_count
        if self.seed is not None:
            result["seed"] = self.seed
        if self.logprobs is not None:
            result["logprobs"] = self.logprobs
        if self.enable_enhanced_civic_answers is not None:
            result["enableEnhancedCivicAnswers"] = (
                self.enable_enhanced_civic_answers
            )
        if self.speech_config is not None:
            result["speechConfig"] = self.speech_config
        if self.thinking_config is not None:
            result["thinkingConfig"] = self.thinking_config.to_dict()
        if self.media_resolution is not None:
            result["mediaResolution"] = self.media_resolution
        return result


class Adapter(BaseAdapter):
    """An adapter for the Gemini API."""

    def __init__(
        self,
        *,
        auth_key: str,
        model: str,
        base_url: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        generation_config: Optional[GenerationConfig] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_config: Optional[dict[str, Any]] = None,
        safety_settings: Optional[list[dict[str, Any]]] = None,
        system_instruction: Optional[dict[str, Any]] = None,
        cached_content: Optional[str] = None,
    ) -> None:
        """Initializes the Adapter."""
        self._auth_key = auth_key
        self._model = model
        self._base_url = (
            base_url or "https://generativelanguage.googleapis.com/v1beta"
        )
        self._headers = headers or {}
        self._generation_config = generation_config
        self._tools = tools
        self._tool_config = tool_config
        self._safety_settings = safety_settings
        self._system_instruction = system_instruction
        self._cached_content = cached_content

        # Debug logging
        masked_key = (
            f"{auth_key[:10]}...{auth_key[-4:]}"
            if len(auth_key) > 14
            else "EMPTY_OR_SHORT_KEY"
        )
        logger.info(f"Gemini adapter initialized with model: {model}")
        logger.info(f"Gemini API key (masked): {masked_key}")
        logger.info(f"Gemini base URL: {self._base_url}")

    @property
    def provider(self) -> str:
        """Returns the provider name."""
        return "gemini"

    def auth_key(self) -> str:
        """
        Return the authentication key for the adapter.
        """
        return self._auth_key

    def format(self) -> str:
        """
        Return the format for the adapter.
        """
        return "gemini"

    def headers(self) -> dict[str, str]:
        """
        Return the headers for the adapter.
        """
        return self._headers

    def on_call(self, body: dict[str, object]) -> None:
        """
        Modify the request body to include all Gemini-specific parameters.
        """
        # Convert OpenAI-style 'messages' to Gemini's 'contents' format if necessary
        if "messages" in body and "contents" not in body:
            messages = body.pop("messages")
            if isinstance(messages, list):
                body["contents"] = self._convert_messages_to_contents(messages)

        # Add all generation config parameters
        if self._generation_config:
            body["generationConfig"] = self._generation_config.to_dict()

        # Add other Gemini-specific parameters
        if self._tools:
            body["tools"] = self._tools
        if self._tool_config:
            body["toolConfig"] = self._tool_config
        if self._safety_settings:
            body["safetySettings"] = self._safety_settings
        if self._system_instruction:
            body["systemInstruction"] = self._system_instruction
        if self._cached_content:
            body["cachedContent"] = self._cached_content

    def url_infer(self) -> str:
        """Returns the full URL for the API request."""
        # For Gemini, the API key is passed as a query parameter
        url = f"{self._base_url}/models/{self._model}:generateContent?key={self._auth_key}"
        logger.info(
            f"Gemini URL for inference: {url[: url.find('key=') + 4]}{self._auth_key[:10]}...{self._auth_key[-4:]}"
        )
        return url

    def _convert_messages_to_contents(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Convert a list of OpenAI-style messages to Gemini's 'contents' format.
        """
        contents = []
        for message in messages:
            role = message.get("role")
            content = message.get("content")

            # Map 'assistant' role to 'model' for Gemini
            if role == "assistant":
                role = "model"

            if role in ["user", "model"]:
                contents.append({"role": role, "parts": [{"text": content}]})

        return contents
