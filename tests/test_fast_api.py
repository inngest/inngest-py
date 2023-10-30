import json
import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api

from . import base, cases, dev_server, http_proxy, net

_client = inngest.Inngest(
    app_id="fast_api",
    base_url=f"http://{net.HOST}:{dev_server.PORT}",
)

_cases = cases.create_cases(_client, "fast_api")


class TestFastAPI(unittest.TestCase):
    app: fastapi.FastAPI
    dev_server_port: int
    fast_api_client: fastapi.testclient.TestClient
    proxy: http_proxy.Proxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.app = fastapi.FastAPI()
        inngest.fast_api.serve(
            cls.app,
            _client,
            [
                case.fn
                for case in _cases
                # Should always be true but mypy doesn't know that
                if isinstance(case.fn, inngest.Function)
            ],
        )

        cls.fast_api_client = fastapi.testclient.TestClient(cls.app)

    def setUp(self) -> None:
        super().setUp()
        base.set_up(self)
        base.register(self.proxy.port)

    def tearDown(self) -> None:
        super().tearDown()
        base.tear_down(self)

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

if __name__ == "__main__":
    unittest.main()
