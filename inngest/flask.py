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
    result,
    transforms,
)


def serve(
    app: flask.Flask,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    handler = comm.CommHandler(
        base_url=base_url or client.base_url,
        client=client,
        framework=const.Framework.FLASK,
        functions=functions,
        logger=app.logger,
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

        server_kind: const.ServerKind | None = None
        match transforms.to_server_kind(
            headers.get(const.HeaderKey.SERVER_KIND.value, "")
        ):
            case result.Ok(server_kind):
                pass
            case result.Err(_):
                pass

        if flask.request.method == "GET":
            return _to_response(handler.inspect(server_kind))

        if flask.request.method == "POST":
            fn_id = flask.request.args.get("fnId")
            if fn_id is None:
                raise errors.MissingParam("fnId")

            return _to_response(
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
                )
            )

        if flask.request.method == "PUT":
            return _to_response(
                await handler.register(
                    app_url=flask.request.url,
                    server_kind=server_kind,
                )
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

        server_kind: const.ServerKind | None = None
        match transforms.to_server_kind(
            headers.get(const.HeaderKey.SERVER_KIND.value, "")
        ):
            case result.Ok(server_kind):
                pass
            case result.Err(_):
                pass

        if flask.request.method == "GET":
            return _to_response(handler.inspect(server_kind))

        if flask.request.method == "POST":
            fn_id = flask.request.args.get("fnId")
            if fn_id is None:
                raise errors.MissingParam("fnId")

            return _to_response(
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
                )
            )

        if flask.request.method == "PUT":
            return _to_response(
                handler.register_sync(
                    app_url=flask.request.url,
                    server_kind=server_kind,
                )
            )

        # Should be unreachable
        return ""


def _to_response(comm_res: comm.CommResponse) -> flask.Response:
    res = flask.make_response()

    for k, v in comm_res.headers.items():
        res.headers.add_header(k, v)

    res.set_data(json.dumps(comm_res.body))
    res.status_code = comm_res.status_code
    return res
