import dataclasses
import json
import typing

import flask

_Main = typing.Callable[[typing.Any, typing.Any], typing.Any]


@dataclasses.dataclass
class _Context:
    api_host: str


class DigitalOceanSimulator:
    """
    Simulates the DigitalOcean Functions runtime. This is necessary because
    DigitalOcean Functions don't seem to have a local development environment.
    If that's wrong or changes, this class can likely be removed.
    """

    def __init__(self, main: _Main) -> None:
        self.app = _create_app(main)


def _create_app(main: _Main) -> flask.Flask:
    app = flask.Flask(__name__)

    @app.route("/api/inngest", methods=["GET", "POST", "PUT"])
    def handler() -> flask.Response:
        event: dict[str, object] = {
            "http": {
                "body": flask.request.data.decode("utf-8"),
                "headers": dict(flask.request.headers.items()),
                "method": flask.request.method,
                "path": flask.request.path,
                "queryString": flask.request.query_string.decode("utf-8"),
            },
        }

        res = main(
            event,
            _Context(api_host=flask.request.url_root),
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
