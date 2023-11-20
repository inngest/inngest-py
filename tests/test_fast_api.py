import json
import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api
from inngest._internal import const

from . import base, cases, dev_server, http_proxy, net

_cases = cases.create_cases("fast_api")


class TestFastAPI(unittest.TestCase):
    app: fastapi.FastAPI
    client: inngest.Inngest
    dev_server_port: int
    fast_api_client: fastapi.testclient.TestClient
    proxy: http_proxy.Proxy

    def setUp(self) -> None:
        super().setUp()
        dev_server_origin = f"http://{net.HOST}:{dev_server.PORT}"
        self.app = fastapi.FastAPI()
        self.client = inngest.Inngest(
            app_id="fast_api",
            event_api_base_url=dev_server_origin,
        )

        inngest.fast_api.serve(
            self.app,
            self.client,
            [case.fn for case in _cases],
            api_base_url=dev_server_origin,
        )
        self.fast_api_client = fastapi.testclient.TestClient(self.app)
        self.proxy = http_proxy.Proxy(self.on_proxy_request).start()
        base.register(self.proxy.port)

    def tearDown(self) -> None:
        super().tearDown()
        self.proxy.stop()

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        if body is None or len(body) == 0:
            body = json.dumps({}).encode("utf-8")

        new_headers = {key: value[0] for key, value in headers.items()}

        if method == "POST":
            res = self.fast_api_client.post(
                path,
                content=body,
                headers=new_headers,
            )
        elif method == "PUT":
            res = self.fast_api_client.put(
                path,
                content=body,
                headers=new_headers,
            )
        else:
            raise Exception(f"unsupported method: {method}")

        return http_proxy.Response(
            body=res.content,
            headers=dict(res.headers),
            status_code=res.status_code,
        )


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestFastAPI, test_name, case.run_test)


class TestRegistration(unittest.TestCase):
    def test_dev_server_to_prod(self) -> None:
        """Ensure that Dev Server cannot initiate a registration request when in
        production mode.
        """
        client = inngest.Inngest(
            app_id="fast_api_registration",
            event_key="test",
            is_production=True,
        )

        @inngest.create_function(
            fn_id="foo",
            retries=0,
            trigger=inngest.TriggerEvent(event="app/foo"),
        )
        async def fn(
            ctx: inngest.Context,
            step: inngest.Step,
        ) -> None:
            pass

        app = fastapi.FastAPI()
        inngest.fast_api.serve(
            app,
            client,
            [fn],
            signing_key="signkey-prod-0486c9",
        )
        fast_api_client = fastapi.testclient.TestClient(app)
        res = fast_api_client.put(
            "/api/inngest",
            headers={
                const.HeaderKey.SERVER_KIND.value.lower(): const.ServerKind.DEV_SERVER.value,
            },
        )
        assert res.status_code == 400
        body: object = res.json()
        assert (
            isinstance(body, dict)
            and body["code"]
            == const.ErrorCode.DISALLOWED_REGISTRATION_INITIATOR.value
        )


if __name__ == "__main__":
    unittest.main()
