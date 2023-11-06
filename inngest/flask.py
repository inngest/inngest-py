"""Flask integration for Inngest."""

import json

import flask

from ._internal import (
    client_lib,
    comm,
    const,
    errors,
    execution,
    function,
    net,
    transforms,
    types,
)

FRAMEWORK = const.Framework.FLASK


def serve(
    app: flask.Flask,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    """
    Serve Inngest functions in a Flask app.

    Args:
    ----
        app: Flask app.
        client: Inngest client.
        functions: List of functions to serve.

        base_url: Base URL to serve from.
        signing_key: Inngest signing key.
    """
    handler = comm.CommHandler(
        base_url=base_url or client.base_url,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        signing_key=signing_key,
    )

    async_mode = any(
        function.is_handler_async or function.is_on_failure_handler_async
        for function in functions
    )
    if async_mode:
        _create_handler_async(app, client, handler)
    else:
        _create_handler_sync(app, client, handler)


def _create_handler_async(
    app: flask.Flask,
    client: client_lib.Inngest,
    handler: comm.CommHandler,
) -> None:
    @app.route("/api/inngest", methods=["GET", "POST", "PUT"])
    async def inngest_api() -> flask.Response | str:
        headers = net.normalize_headers(dict(flask.request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        if flask.request.method == "GET":
            return _to_response(
                client.logger,
                handler.inspect(server_kind),
            )

        if flask.request.method == "POST":
            fn_id = flask.request.args.get("fnId")
            if fn_id is None:
                raise errors.MissingParamError("fnId")

            return _to_response(
                client.logger,
                await handler.call_function(
                    call=execution.Call.from_dict(
                        json.loads(flask.request.data)
                    ),
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=flask.request.data,
                        headers=headers,
                        is_production=client.is_production,
                    ),
                ),
            )

        if flask.request.method == "PUT":
            return _to_response(
                client.logger,
                await handler.register(
                    app_url=flask.request.url,
                    server_kind=server_kind,
                ),
            )

        # Should be unreachable
        return ""


def _create_handler_sync(
    app: flask.Flask,
    client: client_lib.Inngest,
    handler: comm.CommHandler,
) -> None:
    @app.route("/api/inngest", methods=["GET", "POST", "PUT"])
    def inngest_api() -> flask.Response | str:
        headers = net.normalize_headers(dict(flask.request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        if flask.request.method == "GET":
            return _to_response(
                client.logger,
                handler.inspect(server_kind),
            )

        if flask.request.method == "POST":
            fn_id = flask.request.args.get("fnId")
            if fn_id is None:
                raise errors.MissingParamError("fnId")

            return _to_response(
                client.logger,
                handler.call_function_sync(
                    call=execution.Call.from_dict(
                        json.loads(flask.request.data)
                    ),
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=flask.request.data,
                        headers=headers,
                        is_production=client.is_production,
                    ),
                ),
            )

        if flask.request.method == "PUT":
            return _to_response(
                client.logger,
                handler.register_sync(
                    app_url=flask.request.url,
                    server_kind=server_kind,
                ),
            )

        # Should be unreachable
        return ""


def _to_response(
    logger: types.Logger,
    comm_res: comm.CommResponse,
) -> flask.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm.CommResponse.from_error(logger, FRAMEWORK, body)
        body = json.dumps(comm_res.body)

    return flask.Response(
        response=body.encode("utf-8"),
        headers=comm_res.headers,
        status=comm_res.status_code,
    )
