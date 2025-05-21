import unittest

import flask
import flask.logging
import flask.testing
import inngest
import inngest.flask
from inngest._internal import net, server_lib
from test_core import base


class TestTrustProbe(base.BaseTest):
    def _serve(self, client: inngest.Inngest) -> flask.testing.FlaskClient:
        app = flask.Flask(__name__)
        inngest.flask.serve(
            app,
            client,
            self.create_functions(client),
        )
        return app.test_client()

    def test_signed(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        req_sig = net.sign_request(b"", self.signing_key)
        if isinstance(req_sig, Exception):
            raise req_sig

        res = flask_client.post(
            "/api/inngest?probe=trust",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: req_sig,
            },
        )
        assert res.status_code == 200

        sig_header = res.headers.get(server_lib.HeaderKey.SIGNATURE.value)
        assert sig_header is not None
        assert isinstance(
            net.validate_response_sig(
                body=res.get_data(),
                headers=dict(res.headers),
                mode=server_lib.ServerKind.CLOUD,
                signing_key=self.signing_key,
            ),
            str,
        )

    def test_unsigned(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )
        res = flask_client.post("/api/inngest?probe=trust")
        assert res.status_code == 401
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_unsigned_dev_mode(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                is_production=False,
                signing_key=self.signing_key,
            )
        )
        res = flask_client.post("/api/inngest?probe=trust")
        assert res.status_code == 200
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None

    def test_incorrectly_signed(self) -> None:
        flask_client = self._serve(
            inngest.Inngest(
                app_id="my-app",
                event_key="test",
                signing_key=self.signing_key,
            )
        )

        req_sig = net.sign_request(b"", "wrong")
        if isinstance(req_sig, Exception):
            raise req_sig

        res = flask_client.post(
            "/api/inngest?probe=trust",
            headers={
                server_lib.HeaderKey.SIGNATURE.value: req_sig,
            },
        )
        assert res.status_code == 401
        assert res.headers.get(server_lib.HeaderKey.SIGNATURE.value) is None


if __name__ == "__main__":
    unittest.main()
