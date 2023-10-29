import json

import fastapi

from ._internal import client_lib, comm, const, errors, execution, function, net


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
    async def post_inngest_api(request: fastapi.Request) -> fastapi.Response:
        fn_id: object = request.get("fnId")
        if fn_id is None:
            raise errors.MissingParam("fnId")
        if not isinstance(fn_id, str):
            raise errors.InvalidParam("fnId must be a string")

        body = await request.body()

        return _to_response(
            handler.call_function(
                call=execution.Call.from_dict(json.loads(body)),
                fn_id=fn_id,
                req_sig=net.RequestSignature(
                    body=body,
                    headers=dict(request.headers.items()),
                    is_production=client.is_production,
                ),
            )
        )

    @app.put("/api/inngest")
    async def put_inngest_api(request: fastapi.Request) -> fastapi.Response:
        return _to_response(
            handler.register(
                app_url=str(request.url),
                is_from_dev_server=(
                    request.headers.get(const.HeaderKey.SERVER_KIND.value)
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
