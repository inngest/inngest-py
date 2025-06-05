"""
Django integration for Inngest.
"""

import http
import json
import typing

import django
import django.http
import django.urls
import django.views.decorators.csrf

from ._internal import (
    client_lib,
    comm_lib,
    config_lib,
    const,
    function,
    server_lib,
    transforms,
)

FRAMEWORK = server_lib.Framework.DJANGO


def serve(
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    serve_origin: typing.Optional[str] = None,
    serve_path: typing.Optional[str] = None,
) -> django.urls.URLPattern:
    """
    Serve Inngest functions in a Django app.

    Args:
    ----
        client: Inngest client.
        functions: List of functions to serve.

        async_mode: [DEPRECATED] Whether to serve functions asynchronously.
        serve_origin: Origin to serve Inngest from.
        serve_path: Path to serve Inngest from.
    """

    # Not supported yet.
    streaming = False

    handler = comm_lib.CommHandler(
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        streaming=streaming,
    )

    async_mode = any(
        function.is_handler_async or function.is_on_failure_handler_async
        for function in functions
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
    handler: comm_lib.CommHandler,
    *,
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> django.urls.URLPattern:
    def inngest_api(
        request: django.http.HttpRequest,
    ) -> django.http.HttpResponse:
        comm_req = comm_lib.CommRequest(
            body=request.body,
            headers=dict(request.headers.items()),
            query_params=dict(request.GET.items()),
            raw_request=request,
            request_url=request.build_absolute_uri(),
            serve_origin=serve_origin,
            serve_path=serve_path,
        )

        if request.method == "GET":
            return _to_response(
                client,
                handler.get_sync(comm_req),
            )

        if request.method == "POST":
            return _to_response(
                client,
                handler.post_sync(comm_req),
            )

        if request.method == "PUT":
            return _to_response(
                client,
                handler.put_sync(comm_req),
            )

        return django.http.JsonResponse(
            {"error": "Unsupported method"},
            status=http.HTTPStatus.METHOD_NOT_ALLOWED,
        )

    return django.urls.path(
        _trim_leading_slash(
            config_lib.get_serve_path(serve_path) or const.DEFAULT_SERVE_PATH
        ),
        django.views.decorators.csrf.csrf_exempt(inngest_api),
    )


def _create_handler_async(
    client: client_lib.Inngest,
    handler: comm_lib.CommHandler,
    *,
    serve_origin: typing.Optional[str],
    serve_path: typing.Optional[str],
) -> django.urls.URLPattern:
    major_version = transforms.get_major_version(django.get_version())
    if isinstance(major_version, Exception):
        client.logger.error(major_version)
    else:
        if major_version < 5:
            # Django 5 introduced async support for csrf_exempt
            raise Exception(
                "Django version 5 or higher is required for async mode"
            )

    async def inngest_api(
        request: django.http.HttpRequest,
    ) -> django.http.HttpResponse:
        comm_req = comm_lib.CommRequest(
            body=request.body,
            headers=dict(request.headers.items()),
            query_params=dict(request.GET.items()),
            raw_request=request,
            request_url=request.build_absolute_uri(),
            serve_origin=serve_origin,
            serve_path=serve_path,
        )

        if request.method == "GET":
            return _to_response(
                client,
                handler.get_sync(comm_req),
            )

        if request.method == "POST":
            return _to_response(
                client,
                await handler.post(comm_req),
            )

        if request.method == "PUT":
            return _to_response(
                client,
                await handler.put(comm_req),
            )

        return django.http.JsonResponse(
            {"error": "Unsupported method"},
            status=http.HTTPStatus.METHOD_NOT_ALLOWED,
        )

    return django.urls.path(
        _trim_leading_slash(
            config_lib.get_serve_path(serve_path) or const.DEFAULT_SERVE_PATH
        ),
        django.views.decorators.csrf.csrf_exempt(inngest_api),
    )


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm_lib.CommResponse,
) -> django.http.HttpResponse:
    body = transforms.dump_json(comm_res.body)
    if isinstance(body, Exception):
        comm_res = comm_lib.CommResponse.from_error(client.logger, body)
        body = json.dumps(comm_res.body)

    return django.http.HttpResponse(
        body.encode("utf-8"),
        headers=comm_res.headers,
        status=comm_res.status_code,
    )


def _trim_leading_slash(value: str) -> str:
    return value.lstrip("/")
