import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api
from inngest._internal import net, server_lib
from tests import base


class TestIntrospection(base.BaseTest):
    def _serve(self, client: inngest.Inngest) -> fastapi.testclient.TestClient:
        app = fastapi.FastAPI()
        inngest.fast_api.serve(
            app,
            client,
            self.create_functions(client),
        )
        return fastapi.testclient.TestClient(app)

    def test_signed(self) -> None:
        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        req_sig = net.sign(b"", self.signing_key)
        if isinstance(req_sig, Exception):
            raise req_sig

        res = fast_api_client.post(
            "/api/inngest?probe=trust",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: req_sig,
            },
        )
        assert res.status_code == 200

        sig_header = res.headers.get(server_lib.HeaderKey.SIGNATURE.value)
        assert sig_header is not None
        assert isinstance(
            net.validate_sig(
                body=res.content,
                headers=dict(res.headers),
                mode=server_lib.ServerKind.CLOUD,
                signing_key=self.signing_key,
                signing_key_fallback=None,
            ),
            str,
        )

    def test_unsigned(self) -> None:
        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = fast_api_client.post("/api/inngest?probe=trust")
        assert res.status_code == 401
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_unsigned_dev_mode(self) -> None:
        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                is_production=False,
                signing_key=self.signing_key,
            )
        )
        res = fast_api_client.post("/api/inngest?probe=trust")
        assert res.status_code == 200
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_incorrectly_signed(self) -> None:
        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        req_sig = net.sign(b"", "wrong")
        if isinstance(req_sig, Exception):
            raise req_sig

        res = fast_api_client.post(
            "/api/inngest?probe=trust",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: req_sig,
            },
        )
        assert res.status_code == 401
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None


if __name__ == "__main__":
    unittest.main()
