"""Flask integration for Inngest."""

import json
import typing

import flask

from inngest._internal import (
    client_lib,
    comm_lib,
    function,
    server_lib,
    transforms,
)

FRAMEWORK = server_lib.Framework.FLASK


def serve(
    app: flask.Flask,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
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

        serve_origin: Origin to serve the functions from.
        serve_path: Path to serve the functions from.
    """

    handler = comm_lib.CommHandler(
        client=client,
        framework=FRAMEWORK,
        functions=functions,
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
            serve_origin=serve_origin,
            serve_path=serve_path,
        )
    else:
        _create_handler_sync(
            app,
            client,
            handler,
            serve_origin=serve_origin,
            serve_path=serve_path,
        )


def _create_handler_async(
    app: flask.Flask,
    client: client_lib.Inngest,
    handler: comm_lib.CommHandler,
    *,
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> None:
    @app.route("/api/inngest", methods=["GET", "POST", "PUT"])
    async def inngest_api() -> typing.Union[flask.Response, str]:
        if flask.request.method == "GET":
            return _to_response(
                client,
                handler.inspect(
                    body=flask.request.data,
                    headers=dict(flask.request.headers.items()),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                ),
            )

        if flask.request.method == "POST":
            return _to_response(
                client,
                await handler.call_function(
                    body=flask.request.data,
                    headers=dict(flask.request.headers.items()),
                    query_params=flask.request.args,
                    raw_request=flask.request,
                ),
            )

        if flask.request.method == "PUT":
            return _to_response(
                client,
                handler.register(
                    body=flask.request.data,
                    headers=dict(flask.request.headers.items()),
                    query_params=flask.request.args,
                    request_url=flask.request.url,
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                ),
            )

        # Should be unreachable
        return ""


def _create_handler_sync(
    app: flask.Flask,
    client: client_lib.Inngest,
    handler: comm_lib.CommHandler,
    *,
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> None:
    @app.route("/api/inngest", methods=["GET", "POST", "PUT"])
    def inngest_api() -> typing.Union[flask.Response, str]:
        if flask.request.method == "GET":
            return _to_response(
                client,
                handler.inspect(
                    body=flask.request.data,
                    headers=dict(flask.request.headers.items()),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                ),
            )

        if flask.request.method == "POST":
            return _to_response(
                client,
                handler.call_function_sync(
                    body=flask.request.data,
                    headers=dict(flask.request.headers.items()),
                    query_params=flask.request.args,
                    raw_request=flask.request,
                ),
            )

        if flask.request.method == "PUT":
            return _to_response(
                client,
                handler.register(
                    body=flask.request.data,
                    headers=dict(flask.request.headers.items()),
                    query_params=flask.request.args,
                    request_url=flask.request.url,
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                ),
            )

        # Should be unreachable
        return ""


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm_lib.CommResponse,
) -> flask.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm_lib.CommResponse.from_error(client.logger, body)
        body = json.dumps(comm_res.body)

    return flask.Response(
        headers=comm_res.headers,
        response=body.encode("utf-8"),
        status=comm_res.status_code,
    )
