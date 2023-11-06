"""FastAPI integration for Inngest."""

import json

import fastapi

from ._internal import (
    client_lib,
    comm,
    const,
    execution,
    function,
    net,
    transforms,
    types,
)

FRAMEWORK = const.Framework.FAST_API


def serve(
    app: fastapi.FastAPI,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    """
    Serve Inngest functions in a FastAPI app.

    Args:
    ----
        app: FastAPI app.
        client: Inngest client.
        functions: List of functions to serve.

        base_url: Base URL to serve from.
        signing_key: Inngest signing key.
    """
    handler = comm.CommHandler(
        base_url=base_url or client.base_url,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        signing_key=signing_key,
    )

    @app.get("/api/inngest")
    async def get_api_inngest(
        request: fastapi.Request,
    ) -> fastapi.Response:
        headers = net.normalize_headers(dict(request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        return _to_response(client.logger, handler.inspect(server_kind))

    @app.post("/api/inngest")
    async def post_inngest_api(
        fnId: str,  # noqa: N803
        request: fastapi.Request,
    ) -> fastapi.Response:
        body = await request.body()
        headers = net.normalize_headers(dict(request.headers.items()))

        return _to_response(
            client.logger,
            await handler.call_function(
                call=execution.Call.from_dict(json.loads(body)),
                fn_id=fnId,
                req_sig=net.RequestSignature(
                    body=body,
                    headers=headers,
                    is_production=client.is_production,
                ),
            ),
        )

    @app.put("/api/inngest")
    async def put_inngest_api(request: fastapi.Request) -> fastapi.Response:
        headers = net.normalize_headers(dict(request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        return _to_response(
            client.logger,
            await handler.register(
                app_url=str(request.url),
                server_kind=server_kind,
            ),
        )


def _to_response(
    logger: types.Logger, comm_res: comm.CommResponse
) -> fastapi.responses.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm.CommResponse.from_error(logger, FRAMEWORK, body)
        body = json.dumps(comm_res.body)

    return fastapi.responses.Response(
        content=body.encode("utf-8"),
        headers=comm_res.headers,
        status_code=comm_res.status_code,
    )
