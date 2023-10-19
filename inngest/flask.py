import json

from flask import Flask, make_response, request, Response

from .client import Inngest
from .comm import InngestCommHandler
from .function import Function
from .types import FunctionCall


def serve(app: Flask, client: Inngest, functions: list[Function]) -> None:
    comm = InngestCommHandler(
        client=client,
        framework="flask",
        functions=functions,
    )

    @app.route("/api/inngest", methods=["POST", "PUT"])
    def inngest_api() -> Response | str:
        if request.method == "POST":
            fn_id = request.args.get("fnId")
            if fn_id is None:
                raise Exception("missing fnId")

            res = comm.call_function(
                call=FunctionCall.from_raw(json.loads(request.data)),
                fn_id=fn_id,
            )

            response = make_response()

            for k, v in res.headers.items():
                response.headers.add_header(k, v)

            response.set_data(res.body)
            response.status_code = res.status_code
            return response
        elif request.method == "PUT":
            comm.register()

        return ""
