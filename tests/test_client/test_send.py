import asyncio
import dataclasses
import json
import typing
import unittest

import inngest
import inngest.flask
from inngest._internal import const, errors
from tests import dev_server, http_proxy


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
            event_api_base_url=dev_server.origin,
            event_key=dev_server.event_key,
            signing_key=dev_server.signing_key,
        )

        sends = []
        for _ in range(1000):
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
            event_api_base_url=dev_server.origin,
            event_key=dev_server.event_key,
            signing_key=dev_server.signing_key,
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


if __name__ == "__main__":
    unittest.main()
