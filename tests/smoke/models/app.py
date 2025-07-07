import fastapi
import inngest
import inngest.fast_api

# Import all the individual model test helpers
from models.test_anthropic import (
    handle_test_anthropic_response,
    prepare_test_anthropic,
)
from models.test_deepseek import (
    handle_test_deepseek_response,
    prepare_test_deepseek,
)
from models.test_gemini import (
    handle_gemini_basic_test,
    handle_gemini_conversion_response,
    handle_gemini_error_handling_response,
    handle_gemini_stop_sequences_response,
    handle_gemini_structured_response,
    handle_gemini_thinking_response,
    prepare_gemini_basic_test,
    prepare_gemini_conversion_test,
    prepare_gemini_error_handling_test,
    prepare_gemini_mixed_thinking_test,
    prepare_gemini_pure_thinking_test,
    prepare_gemini_stop_sequences_test,
    prepare_gemini_structured_test,
    prepare_gemini_workflow_test,
)
from models.test_grok import handle_test_grok_response, prepare_test_grok
from models.test_openai import handle_test_openai_response, prepare_test_openai

inngest_client = inngest.Inngest(app_id="smoke-test-model-adapters-app")


@inngest_client.create_function(
    fn_id="all-model-adapters-test",
    trigger=inngest.TriggerEvent(event="test-all-adapters"),
    retries=0,
)
async def test_all_adapters(ctx: inngest.Context) -> dict[str, dict]:
    """
    Orchestrates all model adapter tests sequentially.
    """
    results = {}

    # OpenAI
    try:
        adapter, body = prepare_test_openai()
        response = await ctx.step.ai.infer(
            "test-openai", adapter=adapter, body=body
        )
        results["openai"] = handle_test_openai_response(response)
    except Exception as e:
        results["openai"] = {"success": False, "error": str(e)}

    # Anthropic
    try:
        adapter, body = prepare_test_anthropic()
        response = await ctx.step.ai.infer(
            "test-anthropic", adapter=adapter, body=body
        )
        results["anthropic"] = handle_test_anthropic_response(response)
    except Exception as e:
        results["anthropic"] = {"success": False, "error": str(e)}

    # Grok
    try:
        adapter, body = prepare_test_grok()
        response = await ctx.step.ai.infer(
            "test-grok", adapter=adapter, body=body
        )
        results["grok"] = handle_test_grok_response(response)
    except Exception as e:
        results["grok"] = {"success": False, "error": str(e)}

    # DeepSeek
    try:
        adapter, body = prepare_test_deepseek()
        response = await ctx.step.ai.infer(
            "test-deepseek", adapter=adapter, body=body
        )
        results["deepseek"] = handle_test_deepseek_response(response)
    except Exception as e:
        results["deepseek"] = {"success": False, "error": str(e)}

    # Gemini Basic
    try:
        adapter, body = prepare_gemini_basic_test()
        response = await ctx.step.ai.infer(
            "test-gemini-basic", adapter=adapter, body=body
        )
        results["gemini_basic"] = handle_gemini_basic_test(response)
    except Exception as e:
        results["gemini_basic"] = {"success": False, "error": str(e)}

    # Gemini Enhanced
    results["gemini_enhanced"] = {}
    try:
        adapter, body = prepare_gemini_pure_thinking_test()
        response = await ctx.step.ai.infer(
            "test-gemini-pure-thinking", adapter=adapter, body=body
        )
        results["gemini_enhanced"]["pure_thinking"] = (
            handle_gemini_thinking_response(response)
        )
    except Exception as e:
        results["gemini_enhanced"]["pure_thinking"] = {
            "success": False,
            "error": str(e),
        }

    try:
        adapter, body = prepare_gemini_mixed_thinking_test()
        response = await ctx.step.ai.infer(
            "test-gemini-mixed-thinking", adapter=adapter, body=body
        )
        results["gemini_enhanced"]["mixed_thinking"] = (
            handle_gemini_thinking_response(response)
        )
    except Exception as e:
        results["gemini_enhanced"]["mixed_thinking"] = {
            "success": False,
            "error": str(e),
        }

    try:
        adapter, body = prepare_gemini_workflow_test()
        response = await ctx.step.ai.infer(
            "test-gemini-workflow", adapter=adapter, body=body
        )
        results["gemini_enhanced"]["workflow"] = (
            handle_gemini_thinking_response(response)
        )
    except Exception as e:
        results["gemini_enhanced"]["workflow"] = {
            "success": False,
            "error": str(e),
        }

    try:
        adapter, body = prepare_gemini_structured_test()
        response = await ctx.step.ai.infer(
            "test-gemini-structured", adapter=adapter, body=body
        )
        results["gemini_enhanced"]["structured"] = (
            handle_gemini_structured_response(response)
        )
    except Exception as e:
        results["gemini_enhanced"]["structured"] = {
            "success": False,
            "error": str(e),
        }

    try:
        adapter, body = prepare_gemini_stop_sequences_test()
        response = await ctx.step.ai.infer(
            "test-gemini-stop-sequences", adapter=adapter, body=body
        )
        results["gemini_enhanced"]["stop_sequences"] = (
            handle_gemini_stop_sequences_response(response)
        )
    except Exception as e:
        results["gemini_enhanced"]["stop_sequences"] = {
            "success": False,
            "error": str(e),
        }

    try:
        adapter, body = prepare_gemini_conversion_test()
        response = await ctx.step.ai.infer(
            "test-gemini-conversion", adapter=adapter, body=body
        )
        results["gemini_enhanced"]["conversion"] = (
            handle_gemini_conversion_response(response)
        )
    except Exception as e:
        results["gemini_enhanced"]["conversion"] = {
            "success": False,
            "error": str(e),
        }

    # Gemini Error Handling (run last)
    try:
        adapter, body = prepare_gemini_error_handling_test()
        response = await ctx.step.ai.infer(
            "test-gemini-error-handling", adapter=adapter, body=body
        )
        results["gemini_error_handling"] = (
            handle_gemini_error_handling_response(response)
        )
    except Exception as e:
        results["gemini_error_handling"] = {
            "success": True,
            "error_caught": str(e),
        }

    return results


app = fastapi.FastAPI()
inngest.fast_api.serve(app, inngest_client, [test_all_adapters])
