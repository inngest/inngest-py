import unittest

import flask
import flask.logging
import flask.testing
import pytest

import inngest
import inngest.flask
from inngest._internal import errors

_framework = "flask"
_app_id = f"{_framework}-serve"


class TestServe(unittest.TestCase):
    def test_cloud_mode_without_signing_key(self) -> None:
        """
        When in Cloud mode but no signing key, raise an error.

        This test isn't needed for every framework since it's testing logic in
        CommHandler
        """

        app = flask.Flask(__name__)
        client = inngest.Inngest(app_id=_app_id)

        @client.create_function(
            fn_id="fn",
            trigger=inngest.TriggerEvent(event="event"),
        )
        def fn(ctx: inngest.Context, step: inngest.StepSync) -> None:
            pass

        with pytest.raises(Exception) as err:
            inngest.flask.serve(app, client, [fn])
        assert isinstance(err.value, errors.SigningKeyMissingError)


if __name__ == "__main__":
    unittest.main()
