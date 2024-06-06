"""
Simulator for the DigitalOcean Function runtime.

NOT STABLE! This is an experimental feature and may change in the future. If
you'd like to use it, we recommend copying this file into your source code.
"""

import dataclasses
import json
import typing

import flask

_PATH_PREFIX = "/api/v1/web"
_NAMESPACE = "fn-00000000"
_FUNCTION_NAME = "fake-name"
FULL_PATH = f"{_PATH_PREFIX}/{_NAMESPACE}/{_FUNCTION_NAME}"

_Main = typing.Callable[[typing.Any, typing.Any], typing.Any]


@dataclasses.dataclass
class _Context:
    api_host: str
    function_name: str


class DigitalOceanSimulator:
    """
    Simulator for the DigitalOcean Function runtime. This is necessary because
    DigitalOcean Functions don't seem to have a local development environment.
    If that's wrong or changes, this class can likely be deleted.
    """

    def __init__(self, main: _Main) -> None:
        """
        Args:
        ----
            main: DigitalOcean Function handler.
        """
        self.app = _create_app(main)


def _create_app(main: _Main) -> flask.Flask:
    app = flask.Flask(__name__)

    @app.route(FULL_PATH, methods=["GET", "POST", "PUT"])
    def handler() -> flask.Response:
        event: dict[str, object] = {
            "http": {
                "body": flask.request.data.decode("utf-8"),
                "headers": dict(flask.request.headers.items()),
                "method": flask.request.method,
                "path": "",
                "queryString": flask.request.query_string.decode("utf-8"),
            },
        }

        res = main(
            event,
            _Context(
                api_host=flask.request.url_root,
                function_name=f"/{_NAMESPACE}/{_FUNCTION_NAME}",
            ),
        )
        if not isinstance(res, dict):
            raise ValueError("response must be a dict")

        body = None
        if "body" in res:
            body = json.dumps(res["body"])

        headers = res.get("headers", {})
        if not isinstance(headers, dict):
            raise ValueError("headers must be a dict")

        status_code = res.get("statusCode", 200)
        if not isinstance(status_code, int):
            raise ValueError("statusCode must be an int")

        return flask.Response(
            headers=headers,
            response=body,
            status=status_code,
        )

    return app
