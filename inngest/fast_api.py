"""FastAPI integration for Inngest."""

import json
import typing

import fastapi

from ._internal import (
    client_lib,
    comm,
    const,
    execution,
    function,
    net,
    transforms,
)

FRAMEWORK = const.Framework.FAST_API


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

    handler = comm.CommHandler(
        api_base_url=client.api_origin,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        signing_key=client.signing_key,
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
            client,
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
                client,
                comm.CommResponse.from_error(client.logger, call),
                server_kind,
            )

        return _to_response(
            client,
            await handler.call_function(
                call=call,
                fn_id=fnId,
                req_sig=net.RequestSignature(
                    body=body,
                    headers=headers,
                    mode=client._mode,
                ),
                target_hashed_id=stepId,
            ),
            server_kind,
        )

    @app.put("/api/inngest")
    async def put_inngest_api(
        request: fastapi.Request,
    ) -> fastapi.Response:
        headers = net.normalize_headers(dict(request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        sync_id = request.query_params.get(const.QueryParamKey.SYNC_ID.value)

        return _to_response(
            client,
            await handler.register(
                app_url=net.create_serve_url(
                    request_url=str(request.url),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                ),
                server_kind=server_kind,
                sync_id=sync_id,
            ),
            server_kind,
        )


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm.CommResponse,
    server_kind: typing.Union[const.ServerKind, None],
) -> fastapi.responses.Response:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm.CommResponse.from_error(client.logger, body)
        body = json.dumps(comm_res.body)

    return fastapi.responses.Response(
        content=body.encode("utf-8"),
        headers={
            **comm_res.headers,
            **net.create_headers(
                env=client.env,
                framework=FRAMEWORK,
                server_kind=server_kind,
                signing_key=None,
            ),
        },
        status_code=comm_res.status_code,
    )
