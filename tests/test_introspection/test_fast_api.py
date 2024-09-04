import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api
from inngest._internal import server_lib
from tests import base


class TestIntrospection(base.BaseTestIntrospection):
    framework = server_lib.Framework.FAST_API

    def _serve(self, client: inngest.Inngest) -> fastapi.testclient.TestClient:
        app = fastapi.FastAPI()
        inngest.fast_api.serve(
            app,
            client,
            self.create_functions(client),
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
        res = fast_api_client.get(
            "/api/inngest",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: self.create_signature(),
            },
        )
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }
        self.validate_signature(
            res.headers[server_lib.HeaderKey.SIGNATURE.value],
            res.text.encode("utf-8"),
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
        res = fast_api_client.get(
            "/api/inngest",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: self.create_signature(
                    signing_key_fallback
                ),
            },
        )
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }
        print(res.text)
        self.validate_signature(
            res.headers[server_lib.HeaderKey.SIGNATURE.value],
            res.text.encode("utf-8"),
            signing_key_fallback,
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


if __name__ == "__main__":
    unittest.main()
