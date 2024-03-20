"""Flask integration for Inngest."""

import json
import typing

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
)

FRAMEWORK = const.Framework.FLASK


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

    handler = comm.CommHandler(
        api_base_url=client.api_origin,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        signing_key=client.signing_key,
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
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> None:
    @app.route("/api/inngest", methods=["GET", "POST", "PUT"])
    async def inngest_api() -> typing.Union[flask.Response, str]:
        headers = net.normalize_headers(dict(flask.request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        if flask.request.method == "GET":
            return _to_response(
                client,
                handler.inspect(server_kind),
                server_kind,
            )

        if flask.request.method == "POST":
            fn_id = flask.request.args.get(
                const.QueryParamKey.FUNCTION_ID.value
            )
            if fn_id is None:
                raise errors.QueryParamMissingError(
                    const.QueryParamKey.FUNCTION_ID.value
                )

            step_id = flask.request.args.get(const.QueryParamKey.STEP_ID.value)
            if step_id is None:
                raise errors.QueryParamMissingError(
                    const.QueryParamKey.STEP_ID.value
                )

            call = execution.Call.from_raw(json.loads(flask.request.data))
            if isinstance(call, Exception):
                return _to_response(
                    client,
                    comm.CommResponse.from_error(client.logger, call),
                    server_kind,
                )

            return _to_response(
                client,
                await handler.call_function(
                    call=call,
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=flask.request.data,
                        headers=headers,
                        mode=client._mode,
                    ),
                    target_hashed_id=step_id,
                ),
                server_kind,
            )

        if flask.request.method == "PUT":
            return _to_response(
                client,
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
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> None:
    @app.route("/api/inngest", methods=["GET", "POST", "PUT"])
    def inngest_api() -> typing.Union[flask.Response, str]:
        headers = net.normalize_headers(dict(flask.request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        if flask.request.method == "GET":
            return _to_response(
                client,
                handler.inspect(server_kind),
                server_kind,
            )

        if flask.request.method == "POST":
            fn_id = flask.request.args.get(
                const.QueryParamKey.FUNCTION_ID.value
            )
            if fn_id is None:
                raise errors.QueryParamMissingError(
                    const.QueryParamKey.FUNCTION_ID.value
                )

            step_id = flask.request.args.get(const.QueryParamKey.STEP_ID.value)
            if step_id is None:
                raise errors.QueryParamMissingError(
                    const.QueryParamKey.STEP_ID.value
                )

            call = execution.Call.from_raw(json.loads(flask.request.data))
            if isinstance(call, Exception):
                return _to_response(
                    client,
                    comm.CommResponse.from_error(client.logger, call),
                    server_kind,
                )

            return _to_response(
                client,
                handler.call_function_sync(
                    call=call,
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=flask.request.data,
                        headers=headers,
                        mode=client._mode,
                    ),
                    target_hashed_id=step_id,
                ),
                server_kind,
            )

        if flask.request.method == "PUT":
            sync_id = flask.request.args.get(const.QueryParamKey.SYNC_ID.value)

            return _to_response(
                client,
                handler.register_sync(
                    app_url=net.create_serve_url(
                        request_url=flask.request.url,
                        serve_origin=serve_origin,
                        serve_path=serve_path,
                    ),
                    server_kind=server_kind,
                    sync_id=sync_id,
                ),
                server_kind,
            )

        # Should be unreachable
        return ""


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm.CommResponse,
    server_kind: typing.Optional[const.ServerKind],
) -> flask.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm.CommResponse.from_error(client.logger, body)
        body = json.dumps(comm_res.body)

    return flask.Response(
        headers={
            **comm_res.headers,
            **net.create_headers(
                env=client.env,
                framework=FRAMEWORK,
                server_kind=server_kind,
                signing_key=None,
            ),
        },
        response=body.encode("utf-8"),
        status=comm_res.status_code,
    )
