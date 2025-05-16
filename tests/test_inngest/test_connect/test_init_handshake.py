import asyncio
import dataclasses
import os
import typing

import httpx
import inngest
import pytest
import test_core
import test_core.http_proxy
import test_core.net
import test_core.ws_proxy
from inngest.experimental.connect import connect

from .base import BaseTest


class TestAPIRequestHeaders(BaseTest):
    async def test_cloud(self) -> None:
        """
        Connect sends the authorization header in the initial API request.
        """

        @dataclasses.dataclass
        class State:
            outgoing_headers: dict[str, list[str]]

        state = State(outgoing_headers={})

        def mock_api_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            state.outgoing_headers = headers
            return test_core.http_proxy.Response(
                body=b"",
                headers={},
                status_code=200,
            )

        mock_api = test_core.http_proxy.Proxy(mock_api_handler).start()
        self.addCleanup(mock_api.stop)
        client = inngest.Inngest(
            app_id="app",
            api_base_url=mock_api.origin,
            signing_key="deadbeef",
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

        conn = connect(
            [(client, [fn])],
        )
        self.addCleanup(conn.close, wait=True)
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)

        def assert_headers() -> None:
            assert state.outgoing_headers["authorization"] == [
                "Bearer 5f78c33274e43fa9de5659265c1d917e25c03722dcb0b8d27db8d5feaa813953"
            ]

        await test_core.wait_for(assert_headers)

    async def test_cloud_with_signing_key_fallback(self) -> None:
        """
        A 401 response from the API should trigger a retry with the signing key
        fallback.
        """

        @dataclasses.dataclass
        class State:
            attempt_1_auth_header: typing.Optional[str] = None
            attempt_2_auth_header: typing.Optional[str] = None

        state = State()

        def mock_api_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            if state.attempt_1_auth_header is None:
                value = headers.get("authorization")
                assert value is not None
                state.attempt_1_auth_header = value[0]
                return test_core.http_proxy.Response(
                    body=b"",
                    headers={},
                    status_code=401,
                )

            if state.attempt_2_auth_header is None:
                value = headers.get("authorization")
                assert value is not None
                state.attempt_2_auth_header = value[0]

                # Forward request to the Dev Server.
                resp = httpx.request(
                    content=body,
                    headers={k: v[0] for k, v in headers.items()},
                    method=method,
                    url=f"http://0.0.0.0:8288{path}",
                )
                return test_core.http_proxy.Response(
                    body=resp.content,
                    headers={k: v[0] for k, v in resp.headers.items()},
                    status_code=resp.status_code,
                )

            raise Exception("Unexpected number of API requests")

        mock_api = test_core.http_proxy.Proxy(mock_api_handler).start()
        self.addCleanup(mock_api.stop)

        os.environ["INNGEST_SIGNING_KEY_FALLBACK"] = "cafebabe"
        self.addCleanup(lambda: os.environ.pop("INNGEST_SIGNING_KEY_FALLBACK"))
        client = inngest.Inngest(
            app_id="app",
            api_base_url=mock_api.origin,
            signing_key="deadbeef",
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

        conn = connect(
            [(client, [fn])],
        )
        self.addCleanup(conn.close, wait=True)
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)

        def assert_headers() -> None:
            # Signing key.
            assert (
                state.attempt_1_auth_header
                == "Bearer 5f78c33274e43fa9de5659265c1d917e25c03722dcb0b8d27db8d5feaa813953"
            )

            # Signing key fallback.
            assert (
                state.attempt_2_auth_header
                == "Bearer 65ab12a8ff3263fbc257e5ddf0aa563c64573d0bab1f1115b9b107834cfa6971"
            )

        await test_core.wait_for(assert_headers)

    async def test_dev(self) -> None:
        """
        Connect does not send the authorization header in the initial API
        request.
        """

        @dataclasses.dataclass
        class State:
            outgoing_headers: dict[str, list[str]]

        state = State(outgoing_headers={})

        def mock_api_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            state.outgoing_headers = headers
            return test_core.http_proxy.Response(
                body=b"",
                headers={},
                status_code=200,
            )

        mock_api = test_core.http_proxy.Proxy(mock_api_handler).start()
        self.addCleanup(mock_api.stop)
        client = inngest.Inngest(
            app_id="app",
            api_base_url=mock_api.origin,
            is_production=False,
            signing_key="deadbeef",
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context) -> None:
            pass

        conn = connect(
            [(client, [fn])],
        )
        self.addCleanup(conn.close, wait=True)
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)

        await test_core.wait_for_truthy(lambda: state.outgoing_headers)
        assert "authorization" not in state.outgoing_headers

    async def test_start_request_non_retryable_failure(self) -> None:
        """
        Raises an exception when the start request fails non-retryably.
        """

        @dataclasses.dataclass
        class State:
            outgoing_headers: dict[str, list[str]]

        state = State(outgoing_headers={})

        def mock_api_handler(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> test_core.http_proxy.Response:
            state.outgoing_headers = headers
            return test_core.http_proxy.Response(
                body=b"",
                headers={},
                status_code=401,
            )

        mock_api = test_core.http_proxy.Proxy(mock_api_handler).start()
        self.addCleanup(mock_api.stop)
        client = inngest.Inngest(
            app_id="app",
            api_base_url=mock_api.origin,
            is_production=False,
        )

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        async def fn(ctx: inngest.Context, step: inngest.Step) -> None:
            pass

        conn = connect(
            [(client, [fn])],
        )
        self.addCleanup(conn.close, wait=True)
        task = asyncio.create_task(conn.start())
        self.addCleanup(task.cancel)

        with pytest.raises(Exception) as e:
            await task

        assert str(e.value) == "unauthorized"
