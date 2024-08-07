import unittest

import flask
import flask.logging
import flask.testing

import inngest
import inngest.flask
from inngest._internal import server_lib
from tests import base


class TestIntrospection(base.BaseTestIntrospection):
    framework = server_lib.Framework.FLASK

    def _serve(self, client: inngest.Inngest) -> flask.testing.FlaskClient:
        app = flask.Flask(__name__)
        inngest.flask.serve(
            app,
            client,
            self.create_functions(client),
        )
        return app.test_client()

    def test_cloud_mode_with_no_signature(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = flask_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json == {
            **self.expected_unauthed_body,
            "authentication_succeeded": False,
        }
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_cloud_mode_with_signature(self) -> None:
        self.set_signing_key_fallback_env_var()

        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = flask_client.get(
            "/api/inngest",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: self.create_signature(),
            },
        )
        assert res.status_code == 200
        assert res.json == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }
        self.validate_signature(
            res.headers[server_lib.HeaderKey.SIGNATURE.value],
            res.get_data(),
        )

    def test_cloud_mode_with_signature_fallback(self) -> None:
        # Ensure that everything still works when signing with the fallback
        # signing key

        signing_key_fallback = self.set_signing_key_fallback_env_var()

        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = flask_client.get(
            "/api/inngest",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: self.create_signature(
                    signing_key_fallback
                ),
            },
        )
        assert res.status_code == 200
        assert res.json == {
            **self.expected_authed_body,
            "has_signing_key_fallback": True,
        }
        self.validate_signature(
            res.headers[server_lib.HeaderKey.SIGNATURE.value],
            res.get_data(),
            signing_key_fallback,
        )

    def test_dev_mode_with_no_signature(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                is_production=False,
                signing_key=self.signing_key,
            )
        )
        res = flask_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json == {
            **self.expected_unauthed_body,
            "mode": "dev",
        }
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None


if __name__ == "__main__":
    unittest.main()
