import json

import fastapi

from ._internal import client_lib, comm, const, execution, function, net


def serve(
    app: fastapi.FastAPI,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    handler = comm.CommHandler(
        api_origin=base_url or client.base_url,
        client=client,
        framework="flask",
        functions=functions,
        logger=client.logger,
        signing_key=signing_key,
    )

    @app.post("/api/inngest")
    async def post_inngest_api(
        fnId: str,  # pylint: disable=invalid-name
        request: fastapi.Request,
    ) -> fastapi.Response:
        body = await request.body()
        headers = net.normalize_headers(dict(request.headers.items()))

        return _to_response(
            await handler.call_function(
                call=execution.Call.from_dict(json.loads(body)),
                fn_id=fnId,
                req_sig=net.RequestSignature(
                    body=body,
                    headers=headers,
                    is_production=client.is_production,
                ),
            )
        )

    @app.put("/api/inngest")
    async def put_inngest_api(request: fastapi.Request) -> fastapi.Response:
        headers = net.normalize_headers(dict(request.headers.items()))

        return _to_response(
            await handler.register(
                app_url=str(request.url),
                is_from_dev_server=(
                    headers.get(const.HeaderKey.SERVER_KIND.value)
                    == const.ServerKind.DEV_SERVER.value
                ),
            )
        )


def _to_response(comm_res: comm.CommResponse) -> fastapi.responses.JSONResponse:
    return fastapi.responses.JSONResponse(
        content=comm_res.body,
        headers=comm_res.headers,
        status_code=comm_res.status_code,
    )
