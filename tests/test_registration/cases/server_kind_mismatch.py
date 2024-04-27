import inngest
import inngest.fast_api
from inngest._internal import const

from . import base

_TEST_NAME = "server_kind_mismatch"


def create(framework: str) -> base.Case:
    def run_test(self: base.TestCase) -> None:
        """
        Ensure that Dev Server cannot initiate a registration request when the
        SDK is in Cloud mode.
        """

        client = inngest.Inngest(
            app_id=f"{framework}-{_TEST_NAME}",
            event_key="test",
            signing_key="signkey-prod-000000",
        )

        @client.create_function(
            fn_id="dummy",
            retries=0,
            trigger=inngest.TriggerEvent(event="dummy"),
        )
        async def fn(
            ctx: inngest.Context,
            step: inngest.Step,
        ) -> None:
            pass

        self.serve(client, [fn])

        headers = {
            const.HeaderKey.SERVER_KIND.value.lower(): const.ServerKind.DEV_SERVER.value,
        }
        res = self.register(headers)
        assert res.status_code == 400
        assert isinstance(res.body, dict)
        assert res.body["code"] == const.ErrorCode.SERVER_KIND_MISMATCH.value

    return base.Case(
        name=_TEST_NAME,
        run_test=run_test,
    )
