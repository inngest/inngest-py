import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api
from inngest._internal import const
from tests import base


class TestIntrospection(base.BaseTestIntrospection):
    framework = const.Framework.FAST_API

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
                app_id=f"{self.framework.value}-introspection",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = fast_api_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json() == self.expected_unauthed_body

    def test_cloud_mode_with_signature(self) -> None:
        self.set_signing_key_fallback_env_var()

        fast_api_client = self._serve(
            inngest.Inngest(
                app_id=f"{self.framework.value}-introspection",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = fast_api_client.get(
            "/api/inngest",
            headers={
                const.HeaderKey.SIGNATURE.value: self.create_signature(),
            },
        )
        assert res.status_code == 200
        assert res.json() == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }

    def test_dev_mode_with_no_signature(self) -> None:
        fast_api_client = self._serve(
            inngest.Inngest(
                app_id=f"{self.framework.value}-introspection",
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


if __name__ == "__main__":
    unittest.main()
