import logging
import unittest
import unittest.mock

import flask
import flask.testing

import inngest
import inngest.flask
from tests import helper

from . import base, dev_server, http_proxy, net

_logger = unittest.mock.Mock()


class _Middleware(inngest.MiddlewareSync):
    def __init__(self) -> None:
        super().__init__()
        self.call_list: list[str] = []

    def after_run_execution(self) -> None:
        self.call_list.append("after_run_execution")

    def before_response(self) -> None:
        self.call_list.append("before_response")

    def before_run_execution(self) -> None:
        self.call_list.append("before_run_execution")

    def transform_input(self) -> inngest.CallInputTransform:
        self.call_list.append("transform_input")
        return inngest.CallInputTransform(logger=_logger)


@inngest.create_function(
    fn_id="two_steps",
    trigger=inngest.TriggerEvent(event="app/two_steps"),
)
def _two_steps(
    *, logger: logging.Logger, step: inngest.StepSync, **_kwargs: object
) -> None:
    def _first_step() -> None:
        logger.info("first_step")

    step.run("first_step", _first_step)

    def _second_step() -> None:
        logger.info("second_step")

    step.run("second_step", _second_step)


class TestFlask(unittest.TestCase):
    _client: inngest.Inngest
    _middleware: _Middleware
    app: flask.testing.FlaskClient
    dev_server_port: int
    proxy: http_proxy.Proxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls._middleware = _Middleware()

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
            [_two_steps],
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

        # Assert that the middleware hooks were called in the correct order
        assert self._middleware.call_list == [
            "before_run_execution",
            "transform_input",
            "before_response",  # first_step done
            "transform_input",
            "before_response",  # second_step done
            "transform_input",
            "after_run_execution",
            "before_response",  # Function done
        ]

        # Assert that the middleware was able to transform the input
        _logger.info.assert_any_call("first_step")
        _logger.info.assert_any_call("second_step")


if __name__ == "__main__":
    unittest.main()
