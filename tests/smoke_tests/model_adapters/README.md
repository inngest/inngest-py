# AI Model Adapters Smoke Test

This smoke test validates that all AI model adapters work correctly with their respective APIs.

## What it tests

This test calls multiple AI providers to answer a simple question. The purpose of this is to ensure that we:

- Make successful API calls
- Handle provider-specific request formats
- Parse responses correctly

### Models tested:

- **OpenAI** (o4 Mini)
- **Anthropic** (Claude 3 Sonnet)
- **Google Gemini** (Gemini 2.5 Pro)
- **xAI Grok** (Grok 3)
- **DeepSeek** (DeepSeek Chat)

## Setup

1. **Environment Variables**: Copy the example environment variables into a `.env` file located in the root of the inngest-py project and fill in your API keys. Your `.env` file should look like this:

   ```
   INNGEST_BASE_URL=http://localhost:8288
   OPENAI_API_KEY=your_openai_api_key_here
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here
   GROK_API_KEY=your_grok_api_key_here
   DEEPSEEK_API_KEY=your_deepseek_api_key_here
   ```

2. **Virtual Environment**: Make sure you have activated your virtual environment:

   ```bash
   source .venv/bin/activate
   ```

3. **Install Dependencies**: Make sure all dependencies are installed:
   ```bash
   make install
   ```

## Running the test

Navigate to the smoke test directory and run:

```bash
cd tests/smoke_tests/model_adapters
make dev
```

This will:

- Start a FastAPI server on port 8000
- Load your environment variables from the project root `.env` file
- Expose the Inngest function

## Triggering the test

Once the server is running, you can trigger the smoke test by sending an event via the Inngest dev server

## Expected behavior

The test should:

- Successfully call all 5 AI providers
- Return responses from each provider
- Handle any API errors gracefully (displaying error messages instead of crashing)

## Troubleshooting

- **Missing or Invalid API keys**: Make sure all required API keys are set in your `.env` file and are valid
- **Rate Limits**: Some providers may have rate limits; wait a moment and try again
- **API Credits**: Most providers require that you purchase credits. After purchasing, you may need to wait some time for the credits to register on their system.
