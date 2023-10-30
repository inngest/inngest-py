import json

import flask

from ._internal import client_lib, comm, const, errors, execution, function, net


def serve(
    app: flask.Flask,
    client: client_lib.Inngest,
    functions: list[function.FunctionSync],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    handler = comm.CommHandler(
        api_origin=base_url or client.base_url,
        client=client,
        framework="flask",
        functions=functions,
        logger=app.logger,
        signing_key=signing_key,
    )

    @app.route("/api/inngest", methods=["POST", "PUT"])
    def inngest_api() -> flask.Response | str:
        if flask.request.method == "POST":
            fn_id = flask.request.args.get("fnId")
            if fn_id is None:
                raise errors.MissingParam("fnId")

            headers = net.normalize_headers(dict(flask.request.headers.items()))

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
            headers = net.normalize_headers(dict(flask.request.headers.items()))

            return _to_response(
                handler.register_sync(
                    app_url=flask.request.url,
                    is_from_dev_server=(
                        headers.get(const.HeaderKey.SERVER_KIND.value)
                        == const.ServerKind.DEV_SERVER.value
                    ),
                )
            )

        return ""


def _to_response(comm_res: comm.CommResponse) -> flask.Response:
    res = flask.make_response()

    for k, v in comm_res.headers.items():
        res.headers.add_header(k, v)

    res.set_data(json.dumps(comm_res.body))
    res.status_code = comm_res.status_code
    return res
