"""
In-process function requests with a mocked HTTP client, for unit tests.
"""

from __future__ import annotations

import json
import typing

import httpx
import inngest
from inngest._internal import comm_lib, net, run_context, server_lib


class Harness:
    def __init__(self) -> None:
        self.client = inngest.Inngest(
            app_id="evals",
            is_production=False,
            api_base_url="http://sdk.test",
            event_api_base_url="http://sdk.test",
        )
        self.requests: list[httpx.Request] = []
        self.status = 204

        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status)

        transport = httpx.MockTransport(handle)
        self.client._http_client._http_client_sync = httpx.Client(
            transport=transport
        )
        self.client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
            transport=transport
        ).initialize()

    async def request(
        self,
        fn: inngest.Function[typing.Any],
        *,
        memos: dict[str, object] | None = None,
        step_id: str | None = None,
    ) -> tuple[comm_lib.CommResponse, typing.Any]:
        event = inngest.Event(name="start")
        body = {
            "ctx": {
                "run_id": "original",
                "attempt": 0,
                "disable_immediate_execution": False,
                "stack": {"stack": []},
            },
            "event": event.to_dict(),
            "events": [event.to_dict()],
            "steps": memos or {},
            "use_api": False,
        }
        query = {"fnId": fn.id}
        if step_id is not None:
            query["stepId"] = step_id
        req = comm_lib.CommRequest(
            body=json.dumps(body).encode(),
            headers={},
            is_connect=False,
            public_path=None,
            query_params=query,
            raw_request=None,
            request_url="",
            serve_origin=None,
            serve_path=None,
        )
        handler = comm_lib.CommHandler(
            client=self.client,
            enable_unauthed_sync=None,
            framework=server_lib.Framework.FAST_API,
            functions=[fn],
            streaming=None,
        )
        try:
            response = (
                await handler.post(req)
                if fn.is_handler_async
                else handler.post_sync(req)
            )
            encoded = response.body_bytes()
            assert isinstance(encoded, bytes)
            assert run_context.current_run.get() is None
            assert run_context.current_step.get() is None
            assert run_context.current_experiment.get() is None
            return response, json.loads(encoded)
        finally:
            if handler._thread_pool is not None:
                handler._thread_pool.shutdown()
