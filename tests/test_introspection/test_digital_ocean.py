import unittest

import flask
import flask.testing

import inngest
import inngest.digital_ocean
import inngest.fast_api
from inngest._internal import const, digital_ocean_simulator
from tests import base

_framework = const.Framework.DIGITAL_OCEAN.value


class TestIntrospection(base.BaseTestIntrospection):
    def _serve(self, client: inngest.Inngest) -> flask.testing.FlaskClient:
        main = inngest.digital_ocean.serve(
            client,
            self.create_functions(client),
            serve_path="/api/inngest",
        )

        return digital_ocean_simulator.DigitalOceanSimulator(
            main
        ).app.test_client()

    def test_cloud_mode_with_no_signature(self) -> None:
        app_client = self._serve(
            inngest.Inngest(
                app_id=f"{_framework}-introspection",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = app_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json == self.expected_insecure_body

    def test_cloud_mode_with_signature(self) -> None:
        self.set_signing_key_fallback_env_var()

        app_client = self._serve(
            inngest.Inngest(
                app_id=f"{_framework}-introspection",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        res = app_client.get(
            "/api/inngest",
            headers={
                const.HeaderKey.SIGNATURE.value: self.create_signature(),
            },
        )
        assert res.status_code == 200
        assert res.json == self.expected_secure_body

    def test_dev_mode_with_no_signature(self) -> None:
        app_client = self._serve(
            inngest.Inngest(
                app_id=f"{_framework}-introspection",
                event_key="test",
                is_production=False,
                signing_key=self.signing_key,
            )
        )

        res = app_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json == {
            **self.expected_insecure_body,
            "mode": "dev",
        }


if __name__ == "__main__":
    unittest.main()
