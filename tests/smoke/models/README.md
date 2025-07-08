# AI Model Adapters Smoke Test

This smoke test validates that all AI model adapters work correctly with their respective APIs. It runs comprehensive tests across multiple AI providers in parallel for fast execution.

## What it tests

This test suite includes **one main orchestrator function** that runs all model adapter tests in parallel:

### `test_all_adapters` (triggered by `test-all-adapters` event)

This comprehensive test runs **6 model adapter tests simultaneously**:

1.  **OpenAI** - Basic text generation (o4-mini-2025-04-16)
2.  **Anthropic** - Basic text generation (claude-3-5-sonnet-latest)
3.  **Gemini Basic** - Basic text generation (gemini-2.0-flash-exp)
4.  **Gemini Enhanced** - 7 comprehensive feature tests (gemini-2.0-flash-thinking-exp)
5.  **Grok** - Basic text generation (grok-3-latest)
6.  **DeepSeek** - Basic text generation (deepseek-chat)

## Setup

1.  **Environment Variables**: Copy the example environment variables into a `.env` file located in the root of the inngest-py project and fill in your API keys. Your `.env` file should look like this:

    ```
    INNGEST_BASE_URL=http://localhost:8288
    OPENAI_API_KEY=your_openai_api_key_here
    ANTHROPIC_API_KEY=your_anthropic_api_key_here
    GEMINI_API_KEY=your_gemini_api_key_here
    GROK_API_KEY=your_grok_api_key_here
    DEEPSEEK_API_KEY=your_deepseek_api_key_here
    ```

2.  **Virtual Environment**: Make sure you have activated your virtual environment from the project root:

    ```bash
    source .venv/bin/activate
    ```

3.  **Install Dependencies**: Make sure all dependencies are installed:
    ```bash
    make install
    ```

## Running the test

Navigate to the smoke test directory and run:

```bash
cd tests/smoke/models
make dev
```

This will:

- Start a FastAPI server on port 8000
- Load your environment variables from the project root `.env` file
- Expose the orchestrator function

## Triggering the tests

Once the server is running, trigger the comprehensive test by sending a `test-all-adapters` event via the Inngest dev server at `http://localhost:8288`.

## What to expect in the Inngest Dev Console

### ✅ **Successful Test Run**

You should see **one function execution** with the following structure:

```
Function: all-model-adapters-test
Event: test-all-adapters
Status: ✅ Completed
Duration: ~5-10 seconds (parallel execution)
```

### **Expected Response Structure**

The function returns a comprehensive results object with 6 top-level keys:

```json
{
  "openai": { "success": true, "response": "Hello! I'm OpenAI's GPT..." },
  "anthropic": { "success": true, "response": "Hello! I'm Claude..." },
  "gemini": { "success": true, "response": "Hello! I'm Gemini..." },
  "gemini_enhanced": {
    "pure_thinking_test": {
      "success": true,
      "response": "🧠 Reasoning: ... 💡 Answer: ..."
    },
    "mixed_thinking_test": { "success": true, "response": "..." },
    "workflow_test": { "success": true, "response": "..." },
    "structured_test": {
      "success": true,
      "response": "{\"name\":\"...\",\"age\":25,...}"
    },
    "stop_sequences_test": {
      "success": true,
      "response": "1 2 3 4 5",
      "contains_stop": false
    },
    "conversion_test": { "success": true, "response": "8" },
    "error_handling_test": {
      "success": true,
      "error_caught": "API key not valid..."
    }
  },
  "grok": { "success": true, "response": "Hello! I'm Grok..." },
  "deepseek": { "success": true, "response": "Hello! I'm DeepSeek..." }
}
```

## Test Case Details

### **Basic Model Tests (OpenAI, Anthropic, Gemini Basic, Grok, DeepSeek)**

**What they test:**

- ✅ Successful API connection
- ✅ Request format handling
- ✅ Response parsing
- ✅ Basic text generation

**Expected success criteria:**

- `"success": true`
- `"response"` contains meaningful text about the AI model
- `"structure_validation"` shows proper response structure
- `"usage_validation"` shows token count metadata

### **Enhanced Gemini Test Suite**

#### **1. Pure Thinking Test**

- **What it tests**: Gemini's step-by-step reasoning with `thinkingConfig`
- **Expected success**: Response contains both reasoning (🧠) and answer (💡) sections
- **Question**: "Think through this step by step: If I have 15 apples and give away 7, then buy 12 more, how many do I have?"

#### **2. Mixed Thinking Test**

- **What it tests**: Both internal thoughts and final answers
- **Expected success**: Shows thinking process + clear final answer
- **Question**: "Calculate 15 - 7 + 12. Think about it first, then give me the final answer clearly."

#### **3. Workflow Test**

- **What it tests**: Complete thinking workflow with sufficient token budget
- **Expected success**: Contains "20" or "twenty" in response
- **Question**: "What's 8 + 12? Think through it step by step, then give me just the number."

#### **4. Structured Test**

- **What it tests**: JSON schema-based responses
- **Expected success**: Valid JSON with `name`, `age`, `hobbies` fields
- **Question**: "Generate a fictional person profile with name, age, and hobbies."

#### **5. Stop Sequences Test**

- **What it tests**: Proper handling of stop sequences
- **Expected success**: Contains "5" but not "6" or "STOP"
- **Question**: "Count from 1 to 10, but write STOP after 5."

#### **6. Conversion Test**

- **What it tests**: OpenAI-style message format conversion
- **Expected success**: Properly handles conversation history
- **Input**: Multi-turn conversation ending with "What's 5 + 3?"

#### **7. Error Handling Test**

- **What it tests**: Invalid API key handling
- **Expected success**: `"success": true` because error was caught properly
- **Note**: This test intentionally uses invalid credentials

## Expected Behavior Summary

### ✅ **All Tests Pass**

- **Total duration**: ~5-10 seconds (parallel execution)
- **6 model adapters tested simultaneously**
- **All basic tests return `"success": true`**
- **Enhanced Gemini shows 7 sub-tests all passing**
- **Error handling test shows `"success": true` with caught error**

### 🔍 **Key Success Indicators**

1.  **Parallel Execution**: All tests complete in ~5-10 seconds (not 30+ seconds)
2.  **API Connectivity**: All providers return valid responses
3.  **Response Parsing**: All responses properly extracted and formatted
4.  **Gemini Features**: Thinking, structured output, and stop sequences work
5.  **Error Handling**: Invalid credentials properly caught and handled
6.  **Token Validation**: Usage metadata present and valid for all providers

### ❌ **Common Issues**

- **Missing API keys**: Tests return `"success": false` with authentication errors
- **Invalid API keys**: Similar to above, but specific to one provider
- **Rate limits**: Temporary failures, retry after waiting
- **Model availability**: Some models may not be available in all regions

## Troubleshooting

- **Missing or Invalid API keys**: Make sure all required API keys are set in your `.env` file and are valid
- **Rate Limits**: Some providers may have rate limits; wait a moment and try again
- **API Credits**: Most providers require that you purchase credits. After purchasing, you may need to wait some time for the credits to register on their system.
- **Thinking Models**: Enhanced thinking features require Gemini 2.0 series models with thinking capabilities
- **Structured Output**: JSON schema responses may require specific prompting for older models

## New Features Demonstrated

The enhanced Gemini adapter now supports:

✅ **Thinking Features** - Enable step-by-step reasoning with `ThinkingConfig`
✅ **Structured Output** - Get JSON responses with schema validation
✅ **Advanced Generation Controls** - Temperature, top-p, token limits, stop sequences
✅ **System Instructions** - Custom behavior and personality configuration
✅ **Message Format Compatibility** - Seamless OpenAI-to-Gemini conversion
✅ **Comprehensive Error Handling** - Proper API error detection and reporting
✅ **Parallel Execution** - Fast test execution using Inngest's parallel capabilities
