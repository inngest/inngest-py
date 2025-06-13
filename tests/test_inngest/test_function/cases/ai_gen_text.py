import http
import json

import inngest
import test_core.helper
from inngest._internal import server_lib
from inngest.experimental import ai
from test_core import http_proxy

from . import base


class _State(base.BaseState):
    req_body: bytes | None = None
    req_headers: dict[str, list[str]] = {}  # noqa: RUF012
    req_method: str = ""
    req_path: str = ""
    step_output: dict[str, object] | None = None


def create(
    client: inngest.Inngest,
    framework: server_lib.Framework,
    is_sync: bool,
) -> base.Case:
    test_name = base.create_test_name(__file__)
    event_name = base.create_event_name(framework, test_name)
    fn_id = base.create_fn_id(test_name)
    state = _State()

    # Dummy data copy-pasted from a real response
    api_resp_body = {
        "id": "msg_01XhznJBRnxsMVB6N5wSw655",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-5-sonnet-20241022",
        "content": [{"type": "text", "text": "Hi there!"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 9,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 11,
            "service_tier": "standard",
        },
    }

    api_req_body = {
        "messages": [{"role": "user", "content": "Say hi"}],
        "max_tokens": 100,
        "model": "claude-3-5-sonnet-latest",
    }

    def on_request(
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        state.req_body = body
        state.req_headers = headers
        state.req_method = method
        state.req_path = path

        # Dummy headers copy-pasted from a real response
        headers = {
            "Anthropic-Organization-Id": [
                "36a5c0e5-fa82-4899-a2db-49fd0c1af68f"
            ],
            "Anthropic-Ratelimit-Input-Tokens-Limit": ["40000"],
            "Anthropic-Ratelimit-Input-Tokens-Remaining": ["40000"],
            "Anthropic-Ratelimit-Input-Tokens-Reset": ["2025-06-11T16:58:15Z"],
            "Anthropic-Ratelimit-Output-Tokens-Limit": ["8000"],
            "Anthropic-Ratelimit-Output-Tokens-Remaining": ["8000"],
            "Anthropic-Ratelimit-Output-Tokens-Reset": ["2025-06-11T16:58:15Z"],
            "Anthropic-Ratelimit-Requests-Limit": ["50"],
            "Anthropic-Ratelimit-Requests-Remaining": ["49"],
            "Anthropic-Ratelimit-Requests-Reset": ["2025-06-11T16:58:15Z"],
            "Anthropic-Ratelimit-Tokens-Limit": ["48000"],
            "Anthropic-Ratelimit-Tokens-Remaining": ["48000"],
            "Anthropic-Ratelimit-Tokens-Reset": ["2025-06-11T16:58:15Z"],
            "Cf-Cache-Status": ["DYNAMIC"],
            "Cf-Ray": ["94e2a6ef7bfef849-ORD"],
            "Content-Type": ["application/json"],
            "Date": ["Wed, 11 Jun 2025 16:58:15 GMT"],
            "Request-Id": ["req_011CQ2ngskrxA1XyiMMSqrSm"],
            "Server": ["cloudflare"],
            "Strict-Transport-Security": [
                "max-age=31536000; includeSubDomains; preload"
            ],
            "Via": ["1.1 google"],
            "X-Robots-Tag": ["none"],
        }

        return http_proxy.Response(
            body=json.dumps(api_resp_body).encode("utf-8"),
            headers={k: v[0] for k, v in headers.items()},
            status_code=http.HTTPStatus.OK,
        )

    mock_llm = http_proxy.Proxy(on_request)

    adapter = ai.anthropic.Adapter(
        auth_key="sk-ant-api03-000000",
        headers={"x-my-header": "my-value"},
        base_url=mock_llm.origin,
    )

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    def fn_sync(ctx: inngest.ContextSync) -> None:
        state.run_id = ctx.run_id

        state.step_output = ctx.step.ai.gen_text(
            "do-the-thing",
            adapter=adapter,
            body=api_req_body,
        )

    @client.create_function(
        fn_id=fn_id,
        retries=0,
        trigger=inngest.TriggerEvent(event=event_name),
    )
    async def fn_async(ctx: inngest.Context) -> None:
        state.run_id = ctx.run_id

        state.step_output = await ctx.step.ai.gen_text(
            "do-the-thing",
            adapter=adapter,
            body=api_req_body,
        )

    async def run_test(self: base.TestClass) -> None:
        mock_llm.start()
        self.addCleanup(mock_llm.stop)

        self.client.send_sync(inngest.Event(name=event_name))
        run_id = await state.wait_for_run_id()
        await test_core.helper.client.wait_for_run_status(
            run_id,
            test_core.helper.RunStatus.COMPLETED,
        )

        assert state.step_output == api_resp_body
        assert state.req_path == "/messages"
        assert state.req_method == "POST"
        assert state.req_headers["X-Api-Key"] == ["sk-ant-api03-000000"]
        assert state.req_headers["X-My-Header"] == ["my-value"]
        assert state.req_body is not None
        assert json.loads(state.req_body) == api_req_body

    if is_sync:
        fn = fn_sync
    else:
        fn = fn_async

    return base.Case(
        fn=fn,
        run_test=run_test,
        name=test_name,
    )
