"""Flask integration for Inngest."""

import json
import typing

import flask

from inngest._internal import (
    client_lib,
    comm_lib,
    config_lib,
    const,
    function,
    server_lib,
)

FRAMEWORK = server_lib.Framework.FLASK


def serve(
    app: flask.Flask,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    public_path: typing.Optional[str] = None,
    serve_origin: typing.Optional[str] = None,
    serve_path: typing.Optional[str] = None,
) -> None:
    """
    Serve Inngest functions in a Flask app.

    Args:
    ----
        app: Flask app.
        client: Inngest client.
        functions: List of functions to serve.
        public_path: Path that the Inngest server sends requests to. This is only necessary if the SDK is behind a proxy that rewrites the path.
        serve_origin: Origin for serving Inngest functions. This is typically only useful during Docker-based development.
        serve_path: Path for serving Inngest functions. This is only useful if you don't want serve Inngest at the /api/inngest path.
    """

    handler = comm_lib.CommHandler(
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        streaming=const.Streaming.DISABLE,  # Not supported yet.
    )

    async_mode = any(
        function.is_handler_async or function.is_on_failure_handler_async
        for function in functions
    )
    if async_mode:
        _create_handler_async(
            app,
            client,
            handler,
            public_path=public_path,
            serve_origin=serve_origin,
            serve_path=serve_path,
        )
    else:
        _create_handler_sync(
            app,
            client,
            handler,
            public_path=public_path,
            serve_origin=serve_origin,
            serve_path=serve_path,
        )


def _create_handler_async(
    app: flask.Flask,
    client: client_lib.Inngest,
    handler: comm_lib.CommHandler,
    *,
    public_path: typing.Optional[str],
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> None:
    @app.route(
        config_lib.get_serve_path(serve_path) or const.DEFAULT_SERVE_PATH,
        methods=["GET", "POST", "PUT"],
    )
    async def inngest_api() -> typing.Union[flask.Response, str]:
        comm_req = comm_lib.CommRequest(
            body=_get_body_bytes(),
            headers=dict(flask.request.headers.items()),
            public_path=public_path,
            query_params=flask.request.args,
            raw_request=flask.request,
            request_url=flask.request.url,
            serve_origin=serve_origin,
            serve_path=serve_path,
        )

        if flask.request.method == "GET":
            return _to_response(
                client,
                handler.get_sync(comm_req),
            )

        if flask.request.method == "POST":
            return _to_response(
                client,
                await handler.post(comm_req),
            )

        if flask.request.method == "PUT":
            return _to_response(
                client,
                await handler.put(comm_req),
            )

        # Should be unreachable
        return ""


def _create_handler_sync(
    app: flask.Flask,
    client: client_lib.Inngest,
    handler: comm_lib.CommHandler,
    *,
    public_path: typing.Optional[str],
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> None:
    @app.route(
        config_lib.get_serve_path(serve_path) or const.DEFAULT_SERVE_PATH,
        methods=["GET", "POST", "PUT"],
    )
    def inngest_api() -> typing.Union[flask.Response, str]:
        comm_req = comm_lib.CommRequest(
            body=_get_body_bytes(),
            headers=dict(flask.request.headers.items()),
            public_path=public_path,
            query_params=flask.request.args,
            raw_request=flask.request,
            request_url=flask.request.url,
            serve_origin=serve_origin,
            serve_path=serve_path,
        )

        if flask.request.method == "GET":
            return _to_response(
                client,
                handler.get_sync(comm_req),
            )

        if flask.request.method == "POST":
            return _to_response(
                client,
                handler.post_sync(comm_req),
            )

        if flask.request.method == "PUT":
            return _to_response(
                client,
                handler.put_sync(comm_req),
            )

        # Should be unreachable
        return ""


def _get_body_bytes() -> bytes:
    flask.request.get_data(as_text=True)
    return flask.request.data


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm_lib.CommResponse,
) -> flask.Response:
    body = comm_res.body_bytes()
    if isinstance(body, Exception):
        comm_res = comm_lib.CommResponse.from_error(client.logger, body)
        body = json.dumps(comm_res.body).encode("utf-8")

    return flask.Response(
        headers=comm_res.headers,
        response=body,
        status=comm_res.status_code,
    )
