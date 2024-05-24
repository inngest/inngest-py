import unittest

import flask
import flask.testing

import inngest
import inngest.digital_ocean
import inngest.fast_api
from inngest._internal import const
from inngest.experimental import digital_ocean_simulator
from tests import base


class TestIntrospection(base.BaseTestIntrospection):
    framework = const.Framework.DIGITAL_OCEAN

    def _serve(self, client: inngest.Inngest) -> flask.testing.FlaskClient:
        main = inngest.digital_ocean.serve(
            client,
            self.create_functions(client),
        )

        return digital_ocean_simulator.DigitalOceanSimulator(
            main
        ).app.test_client()

    def test_cloud_mode_with_no_signature(self) -> None:
        app_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = app_client.get(digital_ocean_simulator.FULL_PATH)
        assert res.status_code == 200
        assert res.json == {
            **self.expected_unauthed_body,
            "authentication_succeeded": False,
        }

    def test_cloud_mode_with_signature(self) -> None:
        self.set_signing_key_fallback_env_var()

        app_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        res = app_client.get(
            digital_ocean_simulator.FULL_PATH,
            headers={
                const.HeaderKey.SIGNATURE.value: self.create_signature(),
            },
        )
        assert res.status_code == 200
        assert res.json == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }

    def test_dev_mode_with_no_signature(self) -> None:
        app_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                is_production=False,
                signing_key=self.signing_key,
            )
        )

        res = app_client.get(digital_ocean_simulator.FULL_PATH)
        assert res.status_code == 200
        assert res.json == {
            **self.expected_unauthed_body,
            "mode": "dev",
        }


if __name__ == "__main__":
    unittest.main()
