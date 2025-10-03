"""FastAPI integration for Inngest."""

import json
import typing

import fastapi

from ._internal import (
    client_lib,
    comm_lib,
    config_lib,
    const,
    function,
    server_lib,
    transforms,
)

FRAMEWORK = server_lib.Framework.FAST_API


def serve(
    app: fastapi.FastAPI,
    client: client_lib.Inngest,
    functions: list[function.Function[typing.Any]],
    *,
    public_path: str | None = None,
    serve_origin: str | None = None,
    serve_path: str | None = None,
    streaming: const.Streaming | None = None,
) -> None:
    """
    Serve Inngest functions in a FastAPI app.

    Args:
    ----
        app: FastAPI app.
        client: Inngest client.
        functions: List of functions to serve.
        public_path: Path that the Inngest server sends requests to. This is only necessary if the SDK is behind a proxy that rewrites the path.
        serve_origin: Origin for serving Inngest functions. This is typically only useful during Docker-based development.
        serve_path: Path for serving Inngest functions. This is only useful if you don't want serve Inngest at the /api/inngest path.
        streaming: Controls whether to send keepalive bytes until the response is complete.
    """

    handler = comm_lib.CommHandler(
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        streaming=streaming,
    )

    @app.get(config_lib.get_serve_path(serve_path) or const.DEFAULT_SERVE_PATH)
    async def get_api_inngest(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            handler.get_sync(
                comm_lib.CommRequest(
                    body=await request.body(),
                    headers=dict(request.headers.items()),
                    public_path=public_path,
                    query_params=dict(request.query_params.items()),
                    raw_request=request,
                    request_url=str(request.url),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
            ),
        )

    @app.post(config_lib.get_serve_path(serve_path) or const.DEFAULT_SERVE_PATH)
    async def post_inngest_api(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            await handler.post(
                comm_lib.CommRequest(
                    body=await request.body(),
                    headers=dict(request.headers.items()),
                    public_path=public_path,
                    query_params=dict(request.query_params.items()),
                    raw_request=request,
                    request_url=str(request.url),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
            ),
        )

    @app.put(config_lib.get_serve_path(serve_path) or const.DEFAULT_SERVE_PATH)
    async def put_inngest_api(
        request: fastapi.Request,
    ) -> fastapi.Response:
        return _to_response(
            client,
            await handler.put(
                comm_lib.CommRequest(
                    body=await request.body(),
                    headers=dict(request.headers.items()),
                    public_path=public_path,
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
    if comm_res.stream is not None:
        return fastapi.responses.StreamingResponse(
            comm_res.stream(),
            headers=comm_res.headers,
            status_code=comm_res.status_code,
        )

    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm_lib.CommResponse.from_error(client.logger, body)
        body = json.dumps(comm_res.body)

    return fastapi.responses.Response(
        content=body.encode("utf-8"),
        headers=comm_res.headers,
        status_code=comm_res.status_code,
    )
