import dataclasses
import json
import typing

import inngest
import inngest.fast_api
from inngest._internal import server_lib
from tests import http_proxy

from . import base

_TEST_NAME = base.create_test_name(__file__)


def create(framework: server_lib.Framework) -> base.Case:
    def run_test(self: base.TestCase) -> None:
        """
        Ensure the SDK does not respond with privileged info when the sync
        request is unsigned
        """

        @dataclasses.dataclass
        class State:
            headers: dict[str, list[str]]

        state = State(headers={})

        def on_request(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            for k, v in headers.items():
                state.headers[k] = v

            return http_proxy.Response(
                body=json.dumps({}).encode("utf-8"),
                headers={},
                status_code=200,
            )

        mock_cloud = http_proxy.Proxy(on_request).start()
        self.addCleanup(mock_cloud.stop)

        signing_key = "signkey-prod-000000"

        client = inngest.Inngest(
            api_base_url=f"http://localhost:{mock_cloud.port}",
            app_id=f"{framework.value}-{_TEST_NAME}",
            signing_key=signing_key,
        )

        @client.create_function(
            fn_id="foo",
            retries=0,
            trigger=inngest.TriggerEvent(event="app/foo"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
            pass

        self.serve(client, [fn])

        res = self.register()

        assert res.status_code == 200

        assert res.headers.get("Authorization") is None

        assert json.loads(res.body.decode("utf-8")) == {
            "authenticated": False,
            "v": "2024-07-16",
        }

    return base.Case(
        name=_TEST_NAME,
        run_test=run_test,
    )
