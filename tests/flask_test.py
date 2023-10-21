from flask import Flask
from flask.testing import FlaskClient
import inngest

from .base import BaseState, FrameworkTestCase


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


class TestFlask(FrameworkTestCase):
    _app: FlaskClient

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        _app = Flask(__name__)
        _app.logger.disabled = True
        inngest.flask.serve(
            _app,
            cls._client,
            [_no_steps],
        )

        cls._app = _app.test_client()
        cls.register()

    @classmethod
    def on_request(
        cls,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> None:
        cls._app.open(
            method=method,
            path=path,
            headers=headers,
            data=body,
        )

    async def test_no_steps(self) -> None:
        self._client.send(inngest.Event(name="no_steps"))

        def assertion() -> None:
            assert _States.no_steps.is_done()

        await self.wait_for(assertion)
