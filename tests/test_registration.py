import unittest

import fastapi
import fastapi.testclient

import inngest
import inngest.fast_api
from inngest._internal import const


class TestFastAPI(unittest.TestCase):
    def test_dev_server_to_prod(self) -> None:
        """
        Ensure that Dev Server cannot initiate a registration request when in
        production mode.
        """

        client = inngest.Inngest(
            app_id="test",
            event_key="test",
            is_production=True,
        )

        @inngest.create_function(
            fn_id="foo",
            retries=0,
            trigger=inngest.TriggerEvent(event="app/foo"),
        )
        async def fn(**_kwargs: object) -> None:
            pass

        app = fastapi.FastAPI()
        inngest.fast_api.serve(
            app,
            client,
            [fn],
            signing_key="signkey-prod-0486c9",
        )
        fast_api_client = fastapi.testclient.TestClient(app)
        res = fast_api_client.put(
            "/api/inngest",
            headers={
                const.HeaderKey.SERVER_KIND.value.lower(): const.ServerKind.DEV_SERVER.value,
            },
        )
        assert res.status_code == 400
        body: object = res.json()
        assert (
            isinstance(body, dict)
            and body["code"]
            == const.ErrorCode.DISALLOWED_REGISTRATION_INITIATOR.value
        )


if __name__ == "__main__":
    unittest.main()
