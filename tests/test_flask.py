from unittest import TestCase

from flask import Flask
from flask.testing import FlaskClient

import inngest

from .base import (
    BaseState,
    FrameworkTestCase,
    register,
    set_up,
    set_up_class,
    tear_down,
    wait_for,
)
from .http_proxy import HTTPProxy


class _NoStepsState(BaseState):
    counter = 0

    def is_done(self) -> bool:
        return self.counter == 1


class _States:
    no_steps = _NoStepsState()


@inngest.create_function(
    inngest.FunctionOpts(id="no_steps"),
    inngest.TriggerEvent(event="no_steps"),
)
def _no_steps(**_kwargs: object) -> None:
    _States.no_steps.counter += 1


class TestFlask(TestCase, FrameworkTestCase):
    app: FlaskClient
    client: inngest.Inngest
    dev_server_port: int
    http_proxy: HTTPProxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        set_up_class(cls)

        app = Flask(__name__)
        app.logger.disabled = True
        inngest.flask.serve(
            app,
            cls.client,
            [_no_steps],
        )

        cls.app = app.test_client()

    def setUp(self) -> None:
        super().setUp()
        set_up(self)
        register(self.http_proxy.port)

    def tearDown(self) -> None:
        super().tearDown()
        tear_down(self)

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> None:
        self.app.open(
            method=method,
            path=path,
            headers=headers,
            data=body,
        )

    def test_no_steps(self) -> None:
        self.client.send(inngest.Event(name="no_steps"))

        def assertion() -> None:
            assert _States.no_steps.is_done()

        wait_for(assertion)
