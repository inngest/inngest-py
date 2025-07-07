import dataclasses
import json
import typing

import inngest
from inngest._internal import const, server_lib
from test_core import http_proxy

from . import base

_TEST_NAME = base.create_test_name(__file__)


def create(framework: server_lib.Framework) -> base.Case:
    def run_test(self: base.TestCase) -> None:
        """
        Fallback to out-of-band sync when the sync kind header is missing.
        """

        @dataclasses.dataclass
        class State:
            body: typing.Optional[bytes]
            headers: dict[str, list[str]]

        state = State(
            body=None,
            headers={},
        )

        def on_request(
            *,
            body: typing.Optional[bytes],
            headers: dict[str, list[str]],
            method: str,
            path: str,
        ) -> http_proxy.Response:
            for k, v in headers.items():
                state.headers[k] = v

            if body is not None:
                state.body = body

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
        def fn(ctx: inngest.ContextSync) -> None:
            pass

        self.serve(client, [fn])
        res = self.put(body={})
        assert res.status_code == 200
        assert json.loads(res.body.decode("utf-8")) == {}

        assert state.headers.get("authorization") is not None
        assert state.headers.get("x-inngest-env") == ["my-env"]
        assert state.headers.get("x-inngest-framework") == [framework.value]
        assert state.headers.get("x-inngest-sdk") == [
            f"inngest-py:v{const.VERSION}"
        ]

        host: str
        if framework == server_lib.Framework.FAST_API:
            host = "http://testserver"
        elif framework == server_lib.Framework.FLASK:
            host = "http://localhost"
        else:
            raise ValueError(f"unknown framework: {framework}")

        assert state.body is not None
        assert json.loads(state.body.decode("utf-8")) == {
            "appname": client.app_id,
            "capabilities": {
                "connect": "v1",
                "in_band_sync": "v1",
                "trust_probe": "v1",
            },
            "deploy_type": "ping",
            "framework": framework.value,
            "functions": [
                {
                    "id": fn.id,
                    "name": "foo",
                    "steps": {
                        "step": {
                            "id": "step",
                            "name": "step",
                            "retries": {"attempts": 0},
                            "runtime": {
                                "type": "http",
                                "url": f"{host}/api/inngest?fnId={fn.id}&stepId=step",
                            },
                        }
                    },
                    "triggers": [{"event": "app/foo"}],
                }
            ],
            "sdk": f"py:v{const.VERSION}",
            "url": f"{host}/api/inngest",
            "v": "0.1",
        }

    return base.Case(
        name=_TEST_NAME,
        run_test=run_test,
    )
