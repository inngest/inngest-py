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
    api_base_url: str | None = None,
    serve_origin: str | None = None,
    serve_path: str | None = None,
    signing_key: str | None = None,
) -> None:
    """
    Serve Inngest functions in a Flask app.

    Args:
    ----
        app: Flask app.
        client: Inngest client.
        functions: List of functions to serve.

        api_base_url: Origin for the Inngest API.
        serve_origin: Origin to serve the functions from.
        serve_path: Path to serve the functions from.
        signing_key: Inngest signing key.
    """
    handler = comm.CommHandler(
        api_base_url=api_base_url,
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
    handler: comm.CommHandler,
    *,
    serve_origin: str | None,
    serve_path: str | None,
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
                server_kind,
            )

        if flask.request.method == "POST":
            fn_id = flask.request.args.get(
                const.QueryParamKey.FUNCTION_ID.value
            )
            if fn_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.FUNCTION_ID.value
                )

            step_id = flask.request.args.get(const.QueryParamKey.STEP_ID.value)
            if step_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.STEP_ID.value
                )

            call = execution.Call.from_raw(json.loads(flask.request.data))
            if isinstance(call, Exception):
                return _to_response(
                    client.logger,
                    comm.CommResponse.from_error(client.logger, call),
                    server_kind,
                )

            return _to_response(
                client.logger,
                await handler.call_function(
                    call=call,
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=flask.request.data,
                        headers=headers,
                        is_production=client.is_production,
                    ),
                    target_hashed_id=step_id,
                ),
                server_kind,
            )

        if flask.request.method == "PUT":
            return _to_response(
                client.logger,
                await handler.register(
                    app_url=net.create_serve_url(
                        request_url=flask.request.url,
                        serve_origin=serve_origin,
                        serve_path=serve_path,
                    ),
                    server_kind=server_kind,
                ),
                server_kind,
            )

        # Should be unreachable
        return ""


def _create_handler_sync(
    app: flask.Flask,
    client: client_lib.Inngest,
    handler: comm.CommHandler,
    *,
    serve_origin: str | None,
    serve_path: str | None,
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
                server_kind,
            )

        if flask.request.method == "POST":
            fn_id = flask.request.args.get(
                const.QueryParamKey.FUNCTION_ID.value
            )
            if fn_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.FUNCTION_ID.value
                )

            step_id = flask.request.args.get(const.QueryParamKey.STEP_ID.value)
            if step_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.STEP_ID.value
                )

            call = execution.Call.from_raw(json.loads(flask.request.data))
            if isinstance(call, Exception):
                return _to_response(
                    client.logger,
                    comm.CommResponse.from_error(client.logger, call),
                    server_kind,
                )

            return _to_response(
                client.logger,
                handler.call_function_sync(
                    call=call,
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=flask.request.data,
                        headers=headers,
                        is_production=client.is_production,
                    ),
                    target_hashed_id=step_id,
                ),
                server_kind,
            )

        if flask.request.method == "PUT":
            return _to_response(
                client.logger,
                handler.register_sync(
                    app_url=net.create_serve_url(
                        request_url=flask.request.url,
                        serve_origin=serve_origin,
                        serve_path=serve_path,
                    ),
                    server_kind=server_kind,
                ),
                server_kind,
            )

        # Should be unreachable
        return ""


def _to_response(
    logger: types.Logger,
    comm_res: comm.CommResponse,
    server_kind: const.ServerKind | None,
) -> flask.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm.CommResponse.from_error(logger, body)
        body = json.dumps(comm_res.body)

    return flask.Response(
        headers={
            **comm_res.headers,
            **net.create_headers(FRAMEWORK, server_kind),
        },
        response=body.encode("utf-8"),
        status=comm_res.status_code,
    )
