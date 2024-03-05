import json
import threading
import unittest

import tornado.httpclient
import tornado.ioloop
import tornado.log
import tornado.testing
import tornado.web

import inngest
import inngest.tornado
from inngest._internal import const

from . import base, cases, dev_server, net

_framework = "tornado"
_dev_server_origin = f"http://{net.HOST}:{dev_server.PORT}"

_client = inngest.Inngest(
    api_base_url=_dev_server_origin,
    app_id=_framework,
    event_api_base_url=_dev_server_origin,
    is_production=False,
)

_cases = cases.create_sync_cases(_client, _framework)
_fns: list[inngest.Function] = []
for case in _cases:
    if isinstance(case.fn, list):
        _fns.extend(case.fn)
    else:
        _fns.append(case.fn)


# Not using tornado.testing.AsyncHTTPTestCase because it:
# - Does not accept requests to localhost (only 127.0.0.1). This won't work with
#   the Dev Server since sometimes it converts 127.0.0.1 to localhost.
# - Binds to a different random port for each test, which necessitates
#   registration on each test.
class TestTornado(unittest.TestCase):
    client = _client
    tornado_thread: threading.Thread

    @classmethod
    def setUpClass(cls) -> None:
        port = net.get_available_port()

        def start_app() -> None:
            app = tornado.web.Application()
            app.listen(port)
            inngest.tornado.serve(
                app,
                _client,
                _fns,
            )
            tornado.ioloop.IOLoop.current().start()

        cls.tornado_thread = threading.Thread(daemon=True, target=start_app)
        cls.tornado_thread.start()
        base.register(port)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tornado_thread.join(timeout=1)


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestTornado, test_name, case.run_test)


class TestTornadoRegistration(tornado.testing.AsyncHTTPTestCase):
    app: tornado.web.Application = tornado.web.Application()

    def get_app(self) -> tornado.web.Application:
        return self.app

    def test_dev_server_to_prod(self) -> None:
        """
        Ensure that Dev Server cannot initiate a registration request when in
        production mode.
        """

        client = inngest.Inngest(
            app_id=f"{_framework}_registration",
            event_key="test",
            signing_key="signkey-prod-0486c9",
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

        inngest.tornado.serve(
            self.get_app(),
            client,
            [fn],
        )
        res = self.fetch(
            "/api/inngest",
            body=json.dumps({}),
            headers={
                const.HeaderKey.SERVER_KIND.value.lower(): const.ServerKind.DEV_SERVER.value,
            },
            method="PUT",
        )
        assert res.code == 400
        body: object = json.loads(res.body)
        assert (
            isinstance(body, dict)
            and body["code"] == const.ErrorCode.SERVER_KIND_MISMATCH.value
        )


if __name__ == "__main__":
    tornado.testing.main()
