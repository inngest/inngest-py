import json

from flask import Flask, request

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
    def inngest_api():
        if request.method == "POST":
            function_id = request.args.get("fnId")
            if function_id is None:
                raise Exception("missing fnId")

            # step_id = request.args.get("stepId")

            fn_call = FunctionCall.from_raw(json.loads(request.data))
            return comm.call_function(id=function_id, event=fn_call.event)
        elif request.method == "PUT":
            comm.register()

        return ""
