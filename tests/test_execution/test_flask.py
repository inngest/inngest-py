import http
import unittest

import flask
import flask.logging
import flask.testing

import inngest
import inngest.flask
from inngest._internal import server_lib
from tests import base, net


class TestExecution(base.BaseTest):
    def _serve(self, client: inngest.Inngest) -> flask.testing.FlaskClient:
        app = flask.Flask(__name__)
        inngest.flask.serve(
            app,
            client,
            self.create_functions(client),
        )
        return app.test_client()

    def test_no_signature(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = flask_client.post("/api/inngest?fnId=my-fn&stepId=step")
        assert res.status_code == http.HTTPStatus.UNAUTHORIZED
        assert res.json is not None
        assert res.json["code"] == "header_missing"
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_invalid_signature(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        wrong_signing_key = "signkey-prod-111111"
        res = flask_client.post(
            "/api/inngest?fnId=my-fn&stepId=step",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: net.sign_request(
                    b"{}",
                    wrong_signing_key,
                ),
            },
        )
        assert res.status_code == http.HTTPStatus.UNAUTHORIZED
        assert res.json is not None
        assert res.json["code"] == "sig_verification_failed"
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None


if __name__ == "__main__":
    unittest.main()
