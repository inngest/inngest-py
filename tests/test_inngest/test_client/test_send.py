import asyncio
import dataclasses
import json
import time
import typing
import unittest

import httpx
import inngest
from inngest._internal import const, errors
from inngest.experimental import dev_server
from test_core import http_proxy, random_suffix

TEST_HTTPX_TIMEOUT = 1  # timeout in seconds


class TestSend(unittest.IsolatedAsyncioTestCase):
    async def test_send_event_to_cloud_branch_env(self) -> None:
        """
        Test that the SDK sends the correct headers to Cloud.

        We need to use a mock Cloud since the Dev Server doesn't have a mode
        that simulates Cloud.
        """

        @dataclasses.dataclass
        class State:
            headers: dict[str, list[str]]
            path: str

        state = State(headers={}, path="")

        def on_request(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            state.path = path

            for k, v in headers.items():
                state.headers[k] = v

            return http_proxy.Response(
                body=json.dumps({"ids": ["abc123"]}).encode("utf-8"),
                headers={},
                status_code=200,
            )

        mock_cloud = http_proxy.Proxy(on_request).start()
        self.addCleanup(mock_cloud.stop)

        event_key = "event-key-123abc"
        client = inngest.Inngest(
            event_api_base_url=f"http://localhost:{mock_cloud.port}",
            app_id="my-app",
            env="my-env",
            event_key=event_key,
        )

        await client.send(inngest.Event(name="foo"))
        assert state.headers.get("x-inngest-env") == ["my-env"]
        assert state.headers.get("x-inngest-sdk") == [
            f"inngest-py:v{const.VERSION}"
        ]
        assert event_key in state.path

        # Clear test state
        state.headers = {}
        state.path = ""

        client.send_sync(inngest.Event(name="foo"))
        assert state.headers.get("x-inngest-env") == ["my-env"]
        assert state.headers.get("x-inngest-sdk") == [
            f"inngest-py:v{const.VERSION}"
        ]
        assert event_key in state.path

    async def test_many_parallel_sends(self) -> None:
        """
        Ensure the client can run many sends in parallel
        """

        class_name = self.__class__.__name__
        method_name = self._testMethodName
        client = inngest.Inngest(
            app_id=f"{class_name}-{method_name}",
            event_api_base_url=dev_server.server.origin,
            is_production=False,
        )

        sends: list[typing.Coroutine[typing.Any, typing.Any, list[str]]] = []
        for _ in range(500):
            sends.append(
                client.send(inngest.Event(name=f"{class_name}-{method_name}"))
            )

        await asyncio.gather(*sends)

    async def test_cloud_mode_without_event_key(self) -> None:
        client = inngest.Inngest(app_id="my-app")

        with self.assertRaises(errors.EventKeyUnspecifiedError):
            await client.send(inngest.Event(name="foo"))

        with self.assertRaises(errors.EventKeyUnspecifiedError):
            client.send_sync(inngest.Event(name="foo"))

    async def test_partial_send_error(self) -> None:
        """
        Sending bulk events can result in a partial error. For example, sending
        a valid event and an invalid event will result in 1 successfully sent
        event and 1 error
        """

        client = inngest.Inngest(
            app_id="my-app",
            event_key="event-key-123abc",
            event_api_base_url=dev_server.server.origin,
            is_production=False,
        )

        with self.assertRaises(errors.SendEventsError) as ctx:
            await client.send(
                [
                    inngest.Event(name="foo"),
                    inngest.Event(name=""),
                    # This event will not be processed since the previous event
                    # is invalid
                    inngest.Event(name=""),
                ]
            )
        assert len(ctx.exception.ids) == 1

    async def test_client_send_retry(self) -> None:
        """
        Ensure that the client retries on error when sending to event API, and
        that retries use the same idempotency key header.
        """

        test_options: list[
            tuple[
                typing.Callable[[], tuple[http_proxy.OnRequest, CountGetter]],
                bool,
            ]
        ] = [
            (create_first_request_500_handler, True),
            (create_first_request_timeout_handler, True),
            (create_first_request_500_handler, False),
            (create_first_request_timeout_handler, False),
        ]

        for proxy_request_handler_factory, is_sync in test_options:
            with self.subTest(proxy_request_handler_factory):
                on_request, get_proxy_request_counter = (
                    proxy_request_handler_factory()
                )

                proxy = http_proxy.Proxy(on_request)
                proxy.start()
                self.addCleanup(proxy.stop)

                client = inngest.Inngest(
                    event_api_base_url=proxy.origin,
                    app_id=random_suffix("my-app"),
                    is_production=False,
                    request_timeout=TEST_HTTPX_TIMEOUT * 1000,
                )

                # Send two events in one request with the same idempotency key header
                # The returned IDs are unique.
                event_name = random_suffix("foo")
                events = [
                    inngest.Event(name=event_name),
                    inngest.Event(name=event_name),
                ]
                if is_sync:
                    send_ids = client.send_sync(events)
                else:
                    send_ids = await client.send(events)

                assert len(send_ids) == 2
                assert send_ids[0] != send_ids[1]

                # Sleep long enough for the Dev Server to process the events.
                time.sleep(5)  # noqa: ASYNC251

                assert get_proxy_request_counter() == 2

                list_events_resp = httpx.get(  # noqa: ASYNC210
                    f"{dev_server.server.origin}/v1/events",
                    params={"name": event_name},
                )

                # 4 events were stored: 2 from the first attempt and 2 from the second
                # attempt. This isn't ideal but it's the best we can do until we add
                # first-class event idempotency (it's currently enforced when scheduling
                # runs).
                event_ids = [
                    event["internal_id"]
                    for event in list_events_resp.json()["data"]
                ]
                assert len(event_ids) == 4

                # Only 2 unique IDs (despite 4 events) because their internal IDs are
                # deterministically generated from the same seed.
                unique_event_ids = set(event_ids)
                assert len(unique_event_ids) == 2

                # The send IDs match the IDs returned by the REST API.
                assert unique_event_ids == set(send_ids)

    async def test_client_does_not_retry_on_400(self) -> None:
        """
        Ensure that the client does not retry on 400 errors when sending to event API.
        """
        for is_sync in [True, False]:
            with self.subTest(is_sync):
                proxy_request_count = 0

                # Create a proxy that returns a 400
                def on_request(
                    body: typing.Optional[bytes],
                    headers: dict[str, list[str]],
                    method: str,
                    path: str,
                ) -> http_proxy.Response:
                    nonlocal proxy_request_count
                    proxy_request_count += 1

                    return http_proxy.Response(
                        body=b"{}",
                        headers={},
                        status_code=400,
                    )

                proxy = http_proxy.Proxy(on_request)
                proxy.start()
                self.addCleanup(proxy.stop)

                client = inngest.Inngest(
                    event_api_base_url=proxy.origin,
                    app_id=random_suffix("my-app"),
                    is_production=False,
                )

                event_name = random_suffix("foo")
                events = [
                    inngest.Event(name=event_name),
                    inngest.Event(name=event_name),
                ]
                if is_sync:
                    client.send_sync(events)
                else:
                    await client.send(events)

                # client didn't retry request
                assert proxy_request_count == 1


CountGetter = typing.Callable[[], int]


# Create a proxy that mimics a request reaching the Dev Server but the
# client receives a 500 on the first attempt. This ensures that the Dev
# Server's event processing logic properly handles the idempotency key
# header.
def create_first_request_500_handler() -> tuple[
    http_proxy.OnRequest, CountGetter
]:
    proxy_request_count = 0

    def on_request(
        body: typing.Optional[bytes],
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        nonlocal proxy_request_count
        proxy_request_count += 1

        # Always forward request to real dev server
        resp = httpx.request(
            method=method,
            url=f"{dev_server.server.origin}{path}",
            headers={k: v[0] for k, v in headers.items()},
            content=body,
        )

        # But make client think we failed with synthetic 500 response on first try
        if proxy_request_count == 1:
            return http_proxy.Response(
                body=b"{}",
                headers={},
                status_code=500,
            )
        else:
            # forward subsequent dev server responses
            return http_proxy.Response(
                body=resp.content,
                headers=dict(resp.headers),
                status_code=resp.status_code,
            )

    def get_count() -> int:
        return proxy_request_count

    return on_request, get_count


# Create a proxy that mimics a request reaching the Dev Server but the
# client times out on the first attempt.
def create_first_request_timeout_handler() -> tuple[
    http_proxy.OnRequest, CountGetter
]:
    proxy_request_count = 0

    def on_request(
        body: typing.Optional[bytes],
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        nonlocal proxy_request_count
        proxy_request_count += 1

        # Always forward request to real dev server
        resp = httpx.request(
            method=method,
            url=f"{dev_server.server.origin}{path}",
            headers={k: v[0] for k, v in headers.items()},
            content=body,
        )

        # But make client think we timed out
        if proxy_request_count == 1:
            time.sleep(TEST_HTTPX_TIMEOUT + 1)
            # dummy response only used for type checking, client will never receive it
            return http_proxy.Response(
                body=None,
                headers={},
                status_code=418,
            )
        else:
            # forward subsequent dev server responses
            return http_proxy.Response(
                body=resp.content,
                headers=dict(resp.headers),
                status_code=resp.status_code,
            )

    def get_count() -> int:
        return proxy_request_count

    return on_request, get_count


if __name__ == "__main__":
    unittest.main()
