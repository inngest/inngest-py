import json

from flask import Flask, make_response, request, Response

from inngest.client import Inngest
from inngest.comm import CommResponse, CommHandler
from inngest.function import Function
from inngest.execution import Call


def serve(
    app: Flask,
    client: Inngest,
    functions: list[Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    comm = CommHandler(
        api_origin=base_url,
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
                raise Exception("missing fnId")

            return _to_response(
                comm.call_function(
                    call=Call.from_raw(json.loads(request.data)),
                    fn_id=fn_id,
                )
            )
        elif request.method == "PUT":
            return _to_response(
                comm.register(
                    app_url=request.url,
                    # TODO: Find a better way to figure this out.
                    is_from_dev_server=request.environ["REMOTE_ADDR"] == "127.0.0.1",
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
