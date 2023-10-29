import json

import flask

from ._internal import client_lib, comm, const, errors, execution, function, net


def serve(
    app: flask.Flask,
    client: client_lib.Inngest,
    functions: list[function.Function],
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

            return _to_response(
                handler.call_function(
                    call=execution.Call.from_dict(
                        json.loads(flask.request.data)
                    ),
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=flask.request.data,
                        headers=dict(flask.request.headers.items()),
                        is_production=client.is_production,
                    ),
                )
            )

        if flask.request.method == "PUT":
            remote_ip = (
                flask.request.headers.get(const.HeaderKey.REAL_IP.value)
                or flask.request.headers.get(
                    const.HeaderKey.FORWARDED_FOR.value
                )
                or flask.request.environ["REMOTE_ADDR"]
            )

            return _to_response(
                handler.register(
                    app_url=flask.request.url,
                    # TODO: Find a better way to figure this out.
                    is_from_dev_server=remote_ip == "127.0.0.1",
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
