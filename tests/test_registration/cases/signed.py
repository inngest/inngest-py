import dataclasses
import json
import typing

import inngest
import inngest.fast_api
from inngest._internal import const, net, server_lib
from tests import http_proxy

from . import base

_TEST_NAME = base.create_test_name(__file__)


def create(framework: server_lib.Framework) -> base.Case:
    def run_test(self: base.TestCase) -> None:
        """
        Ensure the SDK responds with the function configs when the sync request
        is signed
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

        body = json.dumps(
            {"url": f"http://localhost:{mock_cloud.port}"}
        ).encode("utf-8")
        res = self.register(
            body=body,
            headers={
                "X-Inngest-Server-Kind": "cloud",
                "X-Inngest-Signature": net.sign(
                    body,
                    signing_key,
                ),
            },
        )

        assert res.status_code == 200

        assert res.headers.get("X-Inngest-Env") is None
        assert res.headers.get("X-Inngest-Framework") == framework.value
        assert (
            res.headers.get("X-Inngest-SDK") == f"inngest-py:v{const.VERSION}"
        )
        # # Validate response signature
        assert (
            net.validate_request(
                body=res.body,
                headers=res.headers,
                mode=server_lib.ServerKind.CLOUD,
                signing_key=signing_key,
                signing_key_fallback=None,
            )
            is None
        )

        res_body = json.loads(res.body.decode("utf-8"))

        # Ensure the SDK responded with the function configs
        assert isinstance(res_body, dict)
        functions = res_body.get("functions")
        assert isinstance(functions, list)
        assert len(functions) == 1
        assert res_body.get("v") == "2024-07-16"

    return base.Case(
        name=_TEST_NAME,
        run_test=run_test,
    )