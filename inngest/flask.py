import json

from flask import Flask, Response, make_response, request

from inngest._internal.client import Inngest
from inngest._internal.comm import CommHandler, CommResponse
from inngest._internal.const import HeaderKey
from inngest._internal.errors import MissingParam
from inngest._internal.execution import Call
from inngest._internal.function import Function
from inngest._internal.net import RequestSignature


def serve(
    app: Flask,
    client: Inngest,
    functions: list[Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    comm = CommHandler(
        api_origin=base_url or client.base_url,
        client=client,
        framework="flask",
        functions=functions,
        logger=app.logger,
        signing_key=signing_key,
    )

    @app.route("/api/inngest", methods=["POST", "PUT"])
    def inngest_api() -> Response | str:
        if request.method == "POST":
            fn_id = request.args.get("fnId")
            if fn_id is None:
                raise MissingParam("fnId")

            return _to_response(
                comm.call_function(
                    call=Call.from_dict(json.loads(request.data)),
                    fn_id=fn_id,
                    req_sig=RequestSignature(
                        body=request.data,
                        headers=dict(request.headers.items()),
                        is_production=client.is_production,
                    ),
                )
            )

        if request.method == "PUT":
            remote_ip = (
                request.headers.get(HeaderKey.REAL_IP.value)
                or request.headers.get(HeaderKey.FORWARDED_FOR.value)
                or request.environ["REMOTE_ADDR"]
            )

            return _to_response(
                comm.register(
                    app_url=request.url,
                    # TODO: Find a better way to figure this out.
                    is_from_dev_server=remote_ip == "127.0.0.1",
                )
            )

        return ""


def _to_response(comm_res: CommResponse) -> Response:
    res = make_response()

    for k, v in comm_res.headers.items():
        res.headers.add_header(k, v)

    res.set_data(json.dumps(comm_res.body))
    res.status_code = comm_res.status_code
    return res
