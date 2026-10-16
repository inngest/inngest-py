import asyncio
import datetime
import unittest
import unittest.mock

import httpx

from inngest._internal import net


class TestGetTimeout(unittest.TestCase):
    def test_sync_get_timeout(self) -> None:
        for configured, seconds in [
            (None, 30.0),
            (1500, 1.5),
            (datetime.timedelta(seconds=2.5), 2.5),
            (0, 0.0),
        ]:
            for auth in [False, True]:
                with self.subTest(configured=configured, auth=auth):
                    client = net.AuthenticatedHTTPClient(
                        env=None,
                        request_timeout=configured,
                        signing_key=None,
                        signing_key_fallback=None,
                    )
                    response = httpx.Response(200, json={})
                    target = (
                        "inngest._internal.net.fetch_with_auth_fallback_sync"
                        if auth
                        else None
                    )
                    with unittest.mock.patch(
                        target or "httpx.Client.send", return_value=response
                    ) as send:
                        actual = client.get_sync(
                            "https://example.test/data", auth=auth
                        )
                        request = send.call_args.args[1 if auth else 0]
                        assert actual is response
                        assert request.extensions["timeout"] == dict.fromkeys(
                            ["connect", "read", "write", "pool"], seconds
                        )
                    client._http_client_sync.close()
                    asyncio.run(client._http_client.aclose())

    def test_async_get_timeout(self) -> None:
        async def check() -> None:
            for configured, seconds in [
                (None, 30.0),
                (1500, 1.5),
                (datetime.timedelta(seconds=2.5), 2.5),
                (0, 0.0),
            ]:
                for auth in [False, True]:
                    with self.subTest(configured=configured, auth=auth):
                        client = net.AuthenticatedHTTPClient(
                            env=None,
                            request_timeout=configured,
                            signing_key=None,
                            signing_key_fallback=None,
                        )
                        response = httpx.Response(200, json={})
                        target = (
                            "inngest._internal.net.fetch_with_auth_fallback"
                            if auth
                            else "inngest._internal.net.fetch_with_thready_safety"
                        )
                        with unittest.mock.patch(
                            target,
                            new_callable=unittest.mock.AsyncMock,
                            return_value=response,
                        ) as send:
                            actual = await client.get(
                                "https://example.test/data", auth=auth
                            )
                            request = send.call_args.args[2]
                            assert actual is response
                            assert request.extensions[
                                "timeout"
                            ] == dict.fromkeys(
                                ["connect", "read", "write", "pool"], seconds
                            )
                        client._http_client_sync.close()
                        await client._http_client.aclose()

        asyncio.run(check())
