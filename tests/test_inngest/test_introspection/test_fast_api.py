import unittest

import fastapi
import fastapi.testclient
import inngest
import inngest.fast_api
from inngest._internal import net, server_lib
from test_core import base


class TestIntrospection(base.BaseTestIntrospection):
    framework = server_lib.Framework.FAST_API

    def _serve(
        self,
        client: inngest.Inngest,
        *,
        serve_path: str | None = None,
    ) -> fastapi.testclient.TestClient:
        app = fastapi.FastAPI()
        inngest.fast_api.serve(
            app,
            client,
            self.create_functions(client),
            serve_path=serve_path,
        )
        return fastapi.testclient.TestClient(app)

    def test_cloud_mode_with_no_signature(self) -> None:
        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = fast_api_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_unauthed_body,
            "authentication_succeeded": False,
        }
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_cloud_mode_with_signature(self) -> None:
        self.set_signing_key_fallback_env_var()

        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        req_sig = net.sign_request(b"", self.signing_key)
        if isinstance(req_sig, Exception):
            raise req_sig

        res = fast_api_client.get(
            "/api/inngest",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: req_sig,
            },
        )
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }
        assert isinstance(
            net.validate_response_sig(
                body=res.content,
                headers=dict(res.headers),
                mode=server_lib.ServerKind.CLOUD,
                signing_key=self.signing_key,
            ),
            str,
        )

    def test_cloud_mode_with_signature_fallback(self) -> None:
        # Ensure that everything still works when signing with the fallback
        # signing key

        signing_key_fallback = self.set_signing_key_fallback_env_var()

        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        req_sig = net.sign_request(b"", signing_key_fallback)
        if isinstance(req_sig, Exception):
            raise req_sig

        res = fast_api_client.get(
            "/api/inngest",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: req_sig,
            },
        )
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }

        assert isinstance(
            net.validate_response_sig(
                body=res.content,
                headers=dict(res.headers),
                mode=server_lib.ServerKind.CLOUD,
                signing_key=signing_key_fallback,
            ),
            str,
        )

    def test_dev_mode_with_no_signature(self) -> None:
        fast_api_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                is_production=False,
                signing_key=self.signing_key,
            )
        )
        res = fast_api_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_unauthed_body,
            "mode": "dev",
        }
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_serve_path(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                is_production=False,
                signing_key=self.signing_key,
            ),
            serve_path="/custom/path",
        )
        res = flask_client.get("/custom/path")
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_unauthed_body,
            "mode": "dev",
        }
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None


if __name__ == "__main__":
    unittest.main()
