import dataclasses
import json
import typing

import inngest
import inngest.fast_api
from inngest._internal import const
from tests import http_proxy

from . import base

_TEST_NAME = "cloud_branch_env"


def create(framework: const.Framework) -> base.Case:
    def run_test(self: base.TestCase) -> None:
        """
        Test that the SDK correctly syncs itself with Cloud when using a branch
        environment.

        We need to use a mock Cloud since the Dev Server doesn't have a mode
        that simulates Cloud.
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

        client = inngest.Inngest(
            api_base_url=f"http://localhost:{mock_cloud.port}",
            app_id=f"{framework.value}-{_TEST_NAME}",
            env="my-env",
            signing_key="signkey-prod-0486c9",
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
        res = self.register({})
        assert res.status_code == 200
        assert state.headers.get("Authorization") is not None
        assert state.headers.get("X-Inngest-Env") == ["my-env"]
        assert state.headers.get("X-Inngest-Framework") == [framework.value]
        assert state.headers.get("X-Inngest-SDK") == [
            f"inngest-py:v{const.VERSION}"
        ]

    return base.Case(
        name=_TEST_NAME,
        run_test=run_test,
    )
