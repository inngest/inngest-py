"""FastAPI integration for Inngest."""

import json
import typing

import fastapi

from ._internal import client_lib, comm_lib, function, server_lib, transforms

FRAMEWORK = server_lib.Framework.FAST_API
DEFAULT_SERVE_PATH = "/api/inngest" # should also check environment


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
        client=client,
        framework=FRAMEWORK,
        functions=functions,
    )

    if serve_path is None:
        serve_path = DEFAULT_SERVE_PATH

    @app.get(serve_path)
    async def get_api_inngest(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            handler.get_sync(
                comm_lib.CommRequest(
                    body=await request.body(),
                    headers=dict(request.headers.items()),
                    query_params=dict(request.query_params.items()),
                    raw_request=request,
                    request_url=str(request.url),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
            ),
        )

    @app.post(serve_path)
    async def post_inngest_api(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            await handler.post(
                comm_lib.CommRequest(
                    body=await request.body(),
                    headers=dict(request.headers.items()),
                    query_params=dict(request.query_params.items()),
                    raw_request=request,
                    request_url=str(request.url),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
            ),
        )

    @app.put(serve_path)
    async def put_inngest_api(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            await handler.put(
                comm_lib.CommRequest(
                    body=await request.body(),
                    headers=dict(request.headers.items()),
                    query_params=dict(request.query_params.items()),
                    raw_request=request,
                    request_url=str(request.url),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
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
