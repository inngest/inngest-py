import json

import inngest
import inngest.fast_api
from inngest._internal import server_lib

from . import base

_TEST_NAME = base.create_test_name(__file__)


def create(framework: server_lib.Framework) -> base.Case:
    def run_test(self: base.TestCase) -> None:
        """
        Test that the SDK correctly syncs itself with Cloud when using a branch
        environment.
        """

        signing_key = "signkey-prod-000000"

        client = inngest.Inngest(
            app_id=f"{framework.value}-{_TEST_NAME}",
            env="my-env",
            signing_key=signing_key,
        )

        @client.create_function(
            fn_id="foo",
            retries=0,
            trigger=inngest.TriggerEvent(event="app/foo"),
        )
        def fn(ctx: inngest.ContextSync) -> None:
            pass

        req_body = json.dumps(
            server_lib.InBandSynchronizeRequest(
                url="http://test.local"
            ).to_dict()
        ).encode("utf-8")

        self.serve(client, [fn])
        res = self.put(
            body=req_body,
            headers={
                server_lib.HeaderKey.SYNC_KIND.value: server_lib.SyncKind.IN_BAND.value,
            },
        )
        assert res.status_code == 401
        assert res.headers["x-inngest-env"] == "my-env"
        assert res.headers["x-inngest-expected-server-kind"] == "cloud"
        assert "x-inngest-sync-kind" not in res.headers

        assert json.loads(res.body.decode("utf-8")) == {
            "code": "header_missing",
            "message": "cannot validate signature in production mode without a x-inngest-signature header",
            "name": "HeaderMissingError",
        }

    return base.Case(
        name=_TEST_NAME,
        run_test=run_test,
    )
