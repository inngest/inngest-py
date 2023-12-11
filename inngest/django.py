"""
Django integration for Inngest.
"""

import http
import json

import django
import django.http
import django.urls
import django.views.decorators.csrf

from ._internal import (
    client_lib,
    comm,
    const,
    errors,
    execution,
    function,
    net,
    transforms,
    types,
)

FRAMEWORK = const.Framework.DJANGO


def serve(
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    api_base_url: str | None = None,
    async_mode: bool = False,
    serve_origin: str | None = None,
    serve_path: str | None = None,
    signing_key: str | None = None,
) -> django.urls.URLPattern:
    """
    Serve Inngest functions in a Django app.

    Args:
    ----
        client: Inngest client.
        functions: List of functions to serve.

        api_base_url: Origin for the Inngest API.
        async_mode: Whether to serve functions asynchronously.
        serve_origin: Origin to serve Inngest from.
        serve_path: Path to serve Inngest from.
        signing_key: Inngest signing key.
    """

    handler = comm.CommHandler(
        api_base_url=api_base_url,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        signing_key=signing_key,
    )

    if async_mode:
        return _create_handler_async(
            client,
            handler,
            serve_origin=serve_origin,
            serve_path=serve_path,
        )
    else:
        return _create_handler_sync(
            client,
            handler,
            serve_origin=serve_origin,
            serve_path=serve_path,
        )


def _create_handler_sync(
    client: client_lib.Inngest,
    handler: comm.CommHandler,
    *,
    serve_origin: str | None,
    serve_path: str | None,
) -> django.urls.URLPattern:
    def inngest_api(
        request: django.http.HttpRequest
    ) -> django.http.HttpResponse:
        headers = net.normalize_headers(dict(request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        if request.method == "GET":
            return _to_response(
                client.logger,
                handler.inspect(server_kind),
                server_kind,
            )

        if request.method == "POST":
            fn_id = request.GET.get(const.QueryParamKey.FUNCTION_ID.value)
            if fn_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.FUNCTION_ID.value
                )

            step_id = request.GET.get(const.QueryParamKey.STEP_ID.value)
            if step_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.STEP_ID.value
                )

            call = execution.Call.from_raw(json.loads(request.body))
            if isinstance(call, Exception):
                return _to_response(
                    client.logger,
                    comm.CommResponse.from_error(client.logger, call),
                    server_kind,
                )

            return _to_response(
                client.logger,
                handler.call_function_sync(
                    call=call,
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=request.body,
                        headers=headers,
                        is_production=client.is_production,
                    ),
                    target_hashed_id=step_id,
                ),
                server_kind,
            )

        if request.method == "PUT":
            return _to_response(
                client.logger,
                handler.register_sync(
                    app_url=net.create_serve_url(
                        request_url=request.build_absolute_uri(),
                        serve_origin=serve_origin,
                        serve_path=serve_path,
                    ),
                    server_kind=server_kind,
                ),
                server_kind,
            )

        return django.http.JsonResponse(
            {"error": "Unsupported method"},
            status=http.HTTPStatus.METHOD_NOT_ALLOWED,
        )

    return django.urls.path(
        "api/inngest",
        django.views.decorators.csrf.csrf_exempt(inngest_api),
    )


def _create_handler_async(
    client: client_lib.Inngest,
    handler: comm.CommHandler,
    *,
    serve_origin: str | None,
    serve_path: str | None,
) -> django.urls.URLPattern:
    async def inngest_api(
        request: django.http.HttpRequest
    ) -> django.http.HttpResponse:
        headers = net.normalize_headers(dict(request.headers.items()))

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        if request.method == "GET":
            return _to_response(
                client.logger,
                handler.inspect(server_kind),
                server_kind,
            )

        if request.method == "POST":
            fn_id = request.GET.get(const.QueryParamKey.FUNCTION_ID.value)
            if fn_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.FUNCTION_ID.value
                )

            step_id = request.GET.get(const.QueryParamKey.STEP_ID.value)
            if step_id is None:
                raise errors.MissingParamError(
                    const.QueryParamKey.STEP_ID.value
                )

            call = execution.Call.from_raw(json.loads(request.body))
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
                    fn_id=fn_id,
                    req_sig=net.RequestSignature(
                        body=request.body,
                        headers=headers,
                        is_production=client.is_production,
                    ),
                    target_hashed_id=step_id,
                ),
                server_kind,
            )

        if request.method == "PUT":
            return _to_response(
                client.logger,
                await handler.register(
                    app_url=net.create_serve_url(
                        request_url=request.build_absolute_uri(),
                        serve_origin=serve_origin,
                        serve_path=serve_path,
                    ),
                    server_kind=server_kind,
                ),
                server_kind,
            )

        return django.http.JsonResponse(
            {"error": "Unsupported method"},
            status=http.HTTPStatus.METHOD_NOT_ALLOWED,
        )

    return django.urls.path(
        "api/inngest",
        django.views.decorators.csrf.csrf_exempt(inngest_api),
    )


def _to_response(
    logger: types.Logger,
    comm_res: comm.CommResponse,
    server_kind: const.ServerKind | None,
) -> django.http.HttpResponse:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm.CommResponse.from_error(logger, body)
        body = json.dumps(comm_res.body)

    return django.http.HttpResponse(
        body.encode("utf-8"),
        headers={
            **comm_res.headers,
            **net.create_headers(FRAMEWORK, server_kind),
        },
        status=comm_res.status_code,
    )
