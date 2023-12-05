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
    api_base_url: str | None = None,
    serve_origin: str | None = None,
    serve_path: str | None = None,
    signing_key: str | None = None,
) -> None:
    """
    Serve Inngest functions in a FastAPI app.

    Args:
    ----
        app: FastAPI app.
        client: Inngest client.
        functions: List of functions to serve.

        api_base_url: Origin for the Inngest API.
        serve_origin: Origin to serve the functions from.
        serve_path: Path to serve the functions from.
        signing_key: Inngest signing key.
    """
    handler = comm.CommHandler(
        api_base_url=api_base_url,
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

        return _to_response(
            client.logger,
            handler.inspect(server_kind),
            server_kind,
        )

    @app.post("/api/inngest")
    async def post_inngest_api(
        fnId: str,  # noqa: N803
        stepId: str,  # noqa: N803
        request: fastapi.Request,
    ) -> fastapi.Response:
        body = await request.body()
        headers = net.normalize_headers(dict(request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        call = execution.Call.from_raw(json.loads(body))
        if isinstance(call, Exception):
            return _to_response(
                client.logger,
                comm.CommResponse.from_error(client.logger, call),
                server_kind,
            )

        return _to_response(
            client.logger,
            await handler.call_function(
                call=call,
                fn_id=fnId,
                req_sig=net.RequestSignature(
                    body=body,
                    headers=headers,
                    is_production=client.is_production,
                ),
                target_hashed_id=stepId,
            ),
            server_kind,
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
                app_url=net.create_serve_url(
                    request_url=str(request.url),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                ),
                server_kind=server_kind,
            ),
            server_kind,
        )


def _to_response(
    logger: types.Logger,
    comm_res: comm.CommResponse,
    server_kind: const.ServerKind | None,
) -> fastapi.responses.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm.CommResponse.from_error(logger, body)
        body = json.dumps(comm_res.body)

    return fastapi.responses.Response(
        content=body.encode("utf-8"),
        headers={
            **comm_res.headers,
            **net.create_headers(FRAMEWORK, server_kind),
        },
        status_code=comm_res.status_code,
    )
