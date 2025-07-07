from __future__ import annotations

import typing
from typing import Any, Dict, List, Optional, Union

from .base import BaseAdapter


class ThinkingConfig:
    """
    Configuration options for thinking features in Gemini models.
    
    Thinking features allow the model to use an internal "thinking process" that 
    significantly improves their reasoning and multi-step planning abilities, making 
    them highly effective for complex tasks such as coding, advanced mathematics, 
    and data analysis.
    
    **When to Enable Thinking:**
    - Mathematical problem solving
    - Code debugging and analysis  
    - Multi-step reasoning tasks
    - Research and planning
    - Complex decision making
    
    **Performance Considerations:**
    - Thinking tokens are separate from output tokens
    - Higher budgets = better reasoning but increased cost and latency
    - Dynamic thinking (-1) automatically adjusts based on task complexity
    
    **Supported Models:** Gemini 2.5 series models only.
    """
    
    def __init__(
        self,
        *,
        thinking_budget: Optional[int] = None,
        include_thoughts: Optional[bool] = None,
    ) -> None:
        """
        Args:
        ----
            thinking_budget: The number of thinking tokens to use when generating a response.
                A higher token count generally allows for more detailed reasoning, which can be 
                beneficial for tackling more complex tasks. If latency is more important, use a 
                lower budget or disable thinking by setting thinking_budget to 0.
                
                Setting the thinking_budget to -1 turns on **dynamic thinking**, meaning the model 
                will adjust the budget based on the complexity of the request.
                
                Model-specific ranges:
                - **2.5 Pro**: 128 to 32768 (cannot disable thinking)
                - **2.5 Flash**: 0 to 24576 (thinking_budget = 0 disables thinking)
                - **2.5 Flash Lite**: 512 to 24576 (thinking_budget = 0 disables thinking)
                
                Depending on the prompt, the model might overflow or underflow the token budget.
                
            include_thoughts: Whether to include thought summaries in the response.
                Thought summaries are synthesized versions of the model's raw thoughts and offer 
                insights into the model's internal reasoning process. Note that thinking budgets 
                apply to the model's raw thoughts and not to thought summaries.
                
                When enabled, you can access the summary by iterating through the response 
                parameter's parts, and checking the thought boolean.
        """
        self.thinking_budget = thinking_budget
        self.include_thoughts = include_thoughts
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API request."""
        result = {}
        if self.thinking_budget is not None:
            result["thinkingBudget"] = self.thinking_budget
        if self.include_thoughts is not None:
            result["includeThoughts"] = self.include_thoughts
        return result


class GenerationConfig:
    """
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
        stop_sequences: Optional[List[str]] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Dict[str, Any]] = None,
        response_json_schema: Optional[Any] = None,
        response_modalities: Optional[List[str]] = None,
        candidate_count: Optional[int] = None,
        seed: Optional[int] = None,
        response_logprobs: Optional[bool] = None,
        logprobs: Optional[int] = None,
        enable_enhanced_civic_answers: Optional[bool] = None,
        speech_config: Optional[Dict[str, Any]] = None,
        thinking_config: Optional[ThinkingConfig] = None,
        media_resolution: Optional[str] = None,
    ) -> None:
        """
        Args:
        ----
            temperature: Controls the randomness of the output. Values can range over [0.0, 2.0].
                - 0.0-0.3: Deterministic, factual responses (good for Q&A, analysis)
                - 0.4-0.7: Balanced creativity and consistency (good for general chat)
                - 0.8-1.0: Highly creative responses (good for creative writing)
                - 1.0+: Maximum creativity, may be less coherent
                
            top_p: The maximum cumulative probability of tokens to consider when sampling (nucleus sampling).
                - 0.1-0.3: Very focused responses, less diverse vocabulary
                - 0.8-0.95: Balanced approach (most common)
                - 0.95-1.0: Full vocabulary range
                
            top_k: The maximum number of tokens to consider when sampling.
                - 1-10: Very focused responses (good for factual queries)
                - 20-40: Balanced approach (most common)
                - 40+: More creative responses
                
            max_output_tokens: The maximum number of tokens to include in a response candidate.
                When using thinking models, this limit applies to the final response,
                not the thinking tokens (which are controlled by thinking_budget).
                
            stop_sequences: The set of character sequences (up to 5) that will stop output generation.
                If specified, the API will stop at the first appearance of a stop_sequence.
                
            presence_penalty: Presence penalty applied to the next token's logprobs if the token 
                has already been seen in the response. Range: typically -2.0 to 2.0.
                
            frequency_penalty: Frequency penalty applied to the next token's logprobs, multiplied 
                by the number of times each token has been seen in the response so far.
                
            response_mime_type: MIME type of the generated candidate text.
                - "text/plain": Default text output
                - "application/json": Structured JSON responses
                - "text/x.enum": Enum string responses
                
            response_schema: Output schema of the generated candidate text. Schemas must be a 
                subset of the OpenAPI schema and can be objects, primitives or arrays.
                If set, a compatible response_mime_type must also be set.
                
            response_json_schema: Output schema in JSON Schema format. Alternative to response_schema.
                If set, response_schema must be omitted, but response_mime_type is required.
                
            response_modalities: The requested modalities of the response.
                ⚠️ **Inngest Limitation**: Inngest's step.ai currently only supports text-based 
                responses. While you can request other modalities (images, audio), Inngest 
                workflows cannot process non-text response content.
                
            candidate_count: Number of generated responses to return. Default is 1.
                Note: This doesn't work for previous generation models (Gemini 1.0 family).
                
            seed: Seed used in decoding for reproducible results. If not set, uses random seed.
            
            response_logprobs: If true, export the logprobs results in response.
            
            logprobs: Only valid if response_logprobs=True. Sets the number of top logprobs 
                to return at each decoding step.
                
            enable_enhanced_civic_answers: Enables enhanced civic answers. May not be available for all models.
            
            speech_config: The speech generation config.
                ⚠️ **Inngest Limitation**: Inngest's step.ai currently does not support 
                text-to-speech capabilities. This property can be set but the generated 
                audio output cannot be processed within Inngest workflows.
                
            thinking_config: Config for thinking features. An error will be returned if this field 
                is set for models that don't support thinking. Supported on Gemini 2.5 series models.
                
            media_resolution: If specified, the media resolution specified will be used.
                Options: "MEDIA_RESOLUTION_UNSPECIFIED", "MEDIA_RESOLUTION_LOW", 
                "MEDIA_RESOLUTION_MEDIUM", "MEDIA_RESOLUTION_HIGH"
        """
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
        self.response_logprobs = response_logprobs
        self.logprobs = logprobs
        self.enable_enhanced_civic_answers = enable_enhanced_civic_answers
        self.speech_config = speech_config
        self.thinking_config = thinking_config
        self.media_resolution = media_resolution
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API request."""
        result = {}
        
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
            result["responseJsonSchema"] = self.response_json_schema
        if self.response_modalities is not None:
            result["responseModalities"] = self.response_modalities
        if self.candidate_count is not None:
            result["candidateCount"] = self.candidate_count
        if self.seed is not None:
            result["seed"] = self.seed
        if self.response_logprobs is not None:
            result["responseLogprobs"] = self.response_logprobs
        if self.logprobs is not None:
            result["logprobs"] = self.logprobs
        if self.enable_enhanced_civic_answers is not None:
            result["enableEnhancedCivicAnswers"] = self.enable_enhanced_civic_answers
        if self.speech_config is not None:
            result["speechConfig"] = self.speech_config
        if self.thinking_config is not None:
            result["thinkingConfig"] = self.thinking_config.to_dict()
        if self.media_resolution is not None:
            result["mediaResolution"] = self.media_resolution
            
        return result


class Adapter(BaseAdapter):
    """
    Gemini adapter with comprehensive support for all Gemini API features.
    
    **Basic Usage:**
    ```python
    adapter = Adapter(
        auth_key="your-api-key",
        model="gemini-2.5-flash"
    )
    ```
    
    **With Thinking Features:**
    ```python
    adapter = Adapter(
        auth_key="your-api-key",
        model="gemini-2.5-flash",
        generation_config=GenerationConfig(
            thinking_config=ThinkingConfig(
                thinking_budget=1024,
                include_thoughts=True
            )
        )
    )
    ```
    
    **With Structured Output:**
    ```python
    adapter = Adapter(
        auth_key="your-api-key",
        model="gemini-2.5-flash",
        generation_config=GenerationConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "confidence": {"type": "number"}
                }
            }
        )
    )
    ```
    
    **Supported Models:**
    - gemini-1.5-flash, gemini-1.5-flash-8b, gemini-1.5-pro
    - gemini-1.0-pro
    - gemini-2.0-flash, gemini-2.0-flash-lite  
    - gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite-preview-06-17
    - text-embedding-004, aqa
    """

    def __init__(
        self,
        *,
        auth_key: str,
        model: str,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        generation_config: Optional[GenerationConfig] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_config: Optional[Dict[str, Any]] = None,
        safety_settings: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[Dict[str, Any]] = None,
        cached_content: Optional[str] = None,
    ) -> None:
        """
        Args:
        ----
            auth_key: Gemini API key.
            
            model: Gemini model to use. See supported models in class docstring.
            
            base_url: Gemini API URL. Defaults to official Google API endpoint.
            
            headers: Additional headers to send with the request.
            
            generation_config: Configuration options for model generation and outputs.
                Controls temperature, token limits, thinking features, structured output, etc.
                
            tools: A list of Tools the Model may use to generate the next response.
                **Example:**
                ```python
                tools=[{
                    "functionDeclarations": [{
                        "name": "get_weather",
                        "description": "Get weather information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"}
                            }
                        }
                    }]
                }]
                ```
                
            tool_config: Tool configuration for any Tool specified in the request.
                **Example:**
                ```python
                tool_config={
                    "functionCallingConfig": {
                        "mode": "AUTO",  # or "ANY", "NONE"
                        "allowedFunctionNames": ["get_weather"]
                    }
                }
                ```
                
            safety_settings: A list of unique SafetySetting instances for blocking unsafe content.
                **Example:**
                ```python
                safety_settings=[{
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }]
                ```
                
            system_instruction: Developer set system instruction(s). Currently, text only.
                **Example:**
                ```python
                system_instruction={
                    "parts": [{"text": "You are a helpful assistant."}]
                }
                ```
                
            cached_content: The name of the content cached to use as context to serve the prediction.
                Format: `cachedContents/{cachedContent}`
        """

        self._auth_key = auth_key
        self._headers = headers or {}
        self._model = model
        self._url = (
            base_url or "https://generativelanguage.googleapis.com/v1beta/"
        )
        self._generation_config = generation_config
        self._tools = tools
        self._tool_config = tool_config
        self._safety_settings = safety_settings
        self._system_instruction = system_instruction
        self._cached_content = cached_content

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

    def headers(self) -> Dict[str, str]:
        """
        Return the headers for the adapter.
        """
        return self._headers

    def on_call(self, body: Dict[str, object]) -> None:
        """
        Modify the request body to include all Gemini-specific parameters.
        
        This method structures the request body according to the Gemini API specification,
        including generation config, tools, safety settings, and other advanced features.
        """
        
        # Ensure required contents field exists
        if "contents" not in body:
            # If body has messages (OpenAI-style), convert to Gemini format
            if "messages" in body:
                messages = body.get("messages", [])
                contents = []
                for msg in messages:
                    if isinstance(msg, dict):
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        # Map OpenAI roles to Gemini roles
                        gemini_role = "model" if role == "assistant" else "user"
                        contents.append({
                            "role": gemini_role,
                            "parts": [{"text": str(content)}]
                        })
                body["contents"] = contents
                # Remove OpenAI-style messages field
                body.pop("messages", None)
            else:
                # Fallback: assume single text input
                text_content = ""
                if "prompt" in body:
                    text_content = str(body.pop("prompt"))
                elif "text" in body:
                    text_content = str(body.pop("text"))
                
                body["contents"] = [{"parts": [{"text": text_content}]}]
        
        # Add generation configuration
        if self._generation_config is not None:
            generation_config_dict = self._generation_config.to_dict()
            if generation_config_dict:
                body["generationConfig"] = generation_config_dict
        
        # Add tools
        if self._tools is not None:
            body["tools"] = self._tools
            
        # Add tool configuration
        if self._tool_config is not None:
            body["toolConfig"] = self._tool_config
            
        # Add safety settings
        if self._safety_settings is not None:
            body["safetySettings"] = self._safety_settings
            
        # Add system instruction
        if self._system_instruction is not None:
            body["systemInstruction"] = self._system_instruction
            
        # Add cached content
        if self._cached_content is not None:
            body["cachedContent"] = self._cached_content
        
        # Remove any OpenAI-specific fields that might conflict
        for field in ["model", "max_tokens", "stream"]:
            body.pop(field, None)

    def url_infer(self) -> str:
        """
        Return the URL for generating text with the model included in the path.
        """
        return (
            self._url.rstrip("/")
            + f"/models/{self._model}:generateContent?key={self._auth_key}"
        )
