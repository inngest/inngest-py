import tornado.log
import tornado.testing
from tornado.web import Application

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
    inngest.TriggerEvent(event="tornado/no_steps"),
)
def _no_steps(**_kwargs: object) -> None:
    _States.no_steps.counter += 1


class TestTornado(tornado.testing.AsyncHTTPTestCase, FrameworkTestCase):
    app: Application
    client: inngest.Inngest
    dev_server_port: int
    http_proxy: HTTPProxy

    def get_app(self) -> Application:
        return self.app

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        set_up_class(cls)

        cls.app = Application()
        inngest.tornado.serve(
            cls.app,
            cls.client,
            [_no_steps],
        )

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
        new_headers = {k: v[0] for k, v in headers.items()}
        self.fetch(
            path,
            method=method,
            headers=new_headers,
            body=body,
        )

    def test_no_steps(self) -> None:
        self.client.send(inngest.Event(name="tornado/no_steps"))

        def assertion() -> None:
            assert _States.no_steps.is_done()

        wait_for(assertion)


if __name__ == "__main__":
    tornado.testing.main()
