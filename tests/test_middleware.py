import unittest
import unittest.mock

import flask
import flask.testing

import inngest
import inngest.flask
from tests import helper

from . import base, dev_server, http_proxy, net


@inngest.create_function(
    fn_id="two_steps",
    trigger=inngest.TriggerEvent(event="app/two_steps"),
)
def two_steps(*, step: inngest.StepSync, **_kwargs: object) -> None:
    step.run("first_step", lambda: None)
    step.run("second_step", lambda: None)


class TestFlask(unittest.TestCase):
    app: flask.testing.FlaskClient
    dev_server_port: int
    proxy: http_proxy.Proxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls._middleware = unittest.mock.Mock(spec=inngest.Middleware)

        cls._client = inngest.Inngest(
            app_id="flask",
            base_url=f"http://{net.HOST}:{dev_server.PORT}",
            middleware=[cls._middleware],
        )

        app = flask.Flask(__name__)
        app.logger.disabled = True
        inngest.flask.serve(
            app,
            cls._client,
            [two_steps],
        )
        cls.app = app.test_client()
        cls.proxy = http_proxy.Proxy(cls.on_proxy_request).start()
        base.register(cls.proxy.port)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        cls.proxy.stop()

    @classmethod
    def on_proxy_request(
        cls,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        res = cls.app.open(
            method=method,
            path=path,
            headers=headers,
            data=body,
        )

        return http_proxy.Response(
            body=res.data,
            headers=dict(res.headers),
            status_code=res.status_code,
        )

    def test_middleware(self) -> None:
        event_ids = self._client.send_sync(inngest.Event(name="app/two_steps"))
        run_ids = helper.client.get_run_ids_from_event_id(
            event_ids[0],
            run_count=1,
        )
        helper.client.wait_for_run_status(
            run_ids[0], helper.RunStatus.COMPLETED
        )

        assert self._middleware.before_execution.call_count == 1
        assert self._middleware.after_execution.call_count == 1


if __name__ == "__main__":
    unittest.main()
