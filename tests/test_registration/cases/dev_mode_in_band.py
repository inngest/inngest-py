import json

import inngest
import inngest.fast_api
from inngest._internal import const, server_lib

from . import base

_TEST_NAME = base.create_test_name(__file__)


def create(framework: server_lib.Framework) -> base.Case:
    def run_test(self: base.TestCase) -> None:
        """
        Given:
            SDK mode:       dev
            Sync kind:      in_band

        Perform in-band sync. Request signature doesn't matter.
        """

        client = inngest.Inngest(
            app_id=f"{framework.value}-{_TEST_NAME}",
            env="my-env",
            is_production=False,
        )

        @client.create_function(
            fn_id="foo",
            retries=0,
            trigger=inngest.TriggerEvent(event="app/foo"),
        )
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
            pass

        self.serve(client, [fn], allow_in_band_sync=True)

        req_body = json.dumps(
            server_lib.InBandSynchronizeRequest(
                url="http://test.local"
            ).to_dict()
        ).encode("utf-8")

        res = self.put(
            body=req_body,
            headers={
                server_lib.HeaderKey.SERVER_KIND.value: server_lib.ServerKind.CLOUD.value,
                server_lib.HeaderKey.SYNC_KIND.value: server_lib.SyncKind.IN_BAND.value,
            },
        )
        assert res.status_code == 200
        assert res.headers["x-inngest-env"] == "my-env"
        assert res.headers["x-inngest-expected-server-kind"] == "dev"
        assert res.headers["x-inngest-sync-kind"] == "in_band"

        assert json.loads(res.body.decode("utf-8")) == {
            "app_id": client.app_id,
            "env": "my-env",
            "framework": framework.value,
            "functions": [
                {
                    "batchEvents": None,
                    "cancel": None,
                    "concurrency": None,
                    "debounce": None,
                    "id": fn.id,
                    "idempotency": None,
                    "name": "foo",
                    "priority": None,
                    "rateLimit": None,
                    "steps": {
                        "step": {
                            "id": "step",
                            "name": "step",
                            "retries": {"attempts": 0},
                            "runtime": {
                                "type": "http",
                                "url": f"http://test.local?fnId={fn.id}&stepId=step",
                            },
                        }
                    },
                    "throttle": None,
                    "triggers": [{"event": "app/foo", "expression": None}],
                }
            ],
            "inspection": {
                "schema_version": "2024-05-24",
                "authentication_succeeded": None,
                "function_count": 1,
                "has_event_key": False,
                "has_signing_key": False,
                "has_signing_key_fallback": False,
                "mode": "dev",
            },
            "platform": None,
            "sdk_author": "inngest",
            "sdk_language": "py",
            "sdk_version": const.VERSION,
            "url": "http://test.local",
        }

    return base.Case(
        name=_TEST_NAME,
        run_test=run_test,
    )
