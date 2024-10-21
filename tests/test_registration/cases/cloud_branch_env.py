import json

import inngest
import inngest.fast_api
from inngest._internal import const, net, server_lib

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
        def fn(
            ctx: inngest.Context,
            step: inngest.StepSync,
        ) -> None:
            pass

        self.serve(client, [fn])

        req_body = json.dumps(
            server_lib.InBandSynchronizeRequest(
                url="http://test.local"
            ).to_dict()
        ).encode("utf-8")

        req_sig = net.sign_request(req_body, signing_key)
        if isinstance(req_sig, Exception):
            raise req_sig

        res = self.put(
            body=req_body,
            headers={
                server_lib.HeaderKey.SIGNATURE.value: req_sig,
                server_lib.HeaderKey.SYNC_KIND.value: server_lib.SyncKind.IN_BAND.value,
            },
        )
        assert res.status_code == 200
        assert res.headers["x-inngest-env"] == "my-env"
        assert res.headers["x-inngest-expected-server-kind"] == "cloud"
        assert res.headers["x-inngest-sync-kind"] == "in_band"

        assert isinstance(
            net.validate_response_sig(
                body=res.body,
                headers=res.headers,
                mode=server_lib.ServerKind.CLOUD,
                signing_key=signing_key,
            ),
            str,
        )

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
                "api_origin": "https://api.inngest.com/",
                "app_id": client.app_id,
                "authentication_succeeded": True,
                "capabilities": {"in_band_sync": "v1", "trust_probe": "v1"},
                "env": "my-env",
                "event_api_origin": "https://inn.gs/",
                "event_key_hash": None,
                "framework": framework.value,
                "function_count": 1,
                "has_event_key": False,
                "has_signing_key": True,
                "has_signing_key_fallback": False,
                "mode": "cloud",
                "sdk_language": "py",
                "sdk_version": const.VERSION,
                "serve_origin": None,
                "serve_path": None,
                "signing_key_fallback_hash": None,
                "signing_key_hash": "709e80c88487a2411e1ee4dfb9f22a861492d20c4765150c0c794abd70f8147c",
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
