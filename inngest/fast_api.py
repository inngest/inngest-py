"""FastAPI integration for Inngest."""

import json
import typing

import fastapi

from ._internal import client_lib, comm_lib, function, server_lib, transforms

FRAMEWORK = server_lib.Framework.FAST_API


def serve(
    app: fastapi.FastAPI,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    serve_origin: typing.Optional[str] = None,
    serve_path: typing.Optional[str] = None,
) -> None:
    """
    Serve Inngest functions in a FastAPI app.

    Args:
    ----
        app: FastAPI app.
        client: Inngest client.
        functions: List of functions to serve.

        serve_origin: Origin to serve the functions from.
        serve_path: Path to serve the functions from.
    """

    handler = comm_lib.CommHandler(
        api_base_url=client.api_origin,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
    )

    @app.get("/api/inngest")
    async def get_api_inngest(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            handler.inspect(
                body=await request.body(),
                headers=dict(request.headers.items()),
                serve_origin=serve_origin,
                serve_path=serve_path,
            ),
        )

    @app.post("/api/inngest")
    async def post_inngest_api(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            await handler.call_function(
                body=await request.body(),
                headers=dict(request.headers.items()),
                query_params=dict(request.query_params.items()),
                raw_request=request,
            ),
        )

    @app.put("/api/inngest")
    async def put_inngest_api(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            await handler.register(
                headers=dict(request.headers.items()),
                query_params=dict(request.query_params.items()),
                request_url=str(request.url),
                serve_origin=serve_origin,
                serve_path=serve_path,
            ),
        )


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm_lib.CommResponse,
) -> fastapi.responses.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm_lib.CommResponse.from_error(client.logger, body)
        body = json.dumps(comm_res.body)

    return fastapi.responses.Response(
        content=body.encode("utf-8"),
        headers=comm_res.headers,
        status_code=comm_res.status_code,
    )
