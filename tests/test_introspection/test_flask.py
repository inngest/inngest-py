import unittest

import flask
import flask.logging
import flask.testing

import inngest
import inngest.flask
from inngest._internal import const
from tests import base

_framework = "flask"


class TestIntrospection(base.BaseTestIntrospection):
    def _serve(self, client: inngest.Inngest) -> flask.testing.FlaskClient:
        app = flask.Flask(__name__)
        inngest.flask.serve(
            app,
            client,
            self.create_functions(client),
        )
        return app.test_client()

    def test_insecure(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id=f"{_framework}-introspection",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = flask_client.get("/api/inngest")
        assert res.status_code == 200
        assert res.json == self.expected_insecure_body

    def test_secure(self) -> None:
        self.set_signing_key_fallback_env_var()

        flask_client = self._serve(
            inngest.Inngest(
                app_id=f"{_framework}-introspection",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = flask_client.get(
            "/api/inngest",
            headers={
                const.HeaderKey.SIGNATURE.value: self.create_signature(),
            },
        )
        assert res.status_code == 200
        assert res.json == self.expected_secure_body


if __name__ == "__main__":
    unittest.main()
