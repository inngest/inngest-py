"""
DigitalOcean integration for Inngest
"""

from __future__ import annotations

import json
import typing
import urllib.parse

from ._internal import (
    client_lib,
    comm_lib,
    const,
    errors,
    function,
    server_lib,
    types,
)

FRAMEWORK = server_lib.Framework.DIGITAL_OCEAN


def serve(
    client: client_lib.Inngest,
    functions: list[function.Function[typing.Any]],
    *,
    public_path: str | None = None,
    serve_origin: str | None = None,
    serve_path: str | None = None,
) -> typing.Callable[[dict[str, object], _Context], _Response]:
    """
    Serve Inngest functions in a DigitalOcean Function.

    Args:
    ----
        client: Inngest client.
        functions: List of functions to serve.
        public_path: Path that the Inngest server sends requests to. This is only necessary if the SDK is behind a proxy that rewrites the path.
        serve_origin: Origin for serving Inngest functions. This is typically only useful during Docker-based development.
        serve_path: Path for serving Inngest functions. This is only useful if you don't want serve Inngest at the /api/inngest path.
    """

    handler = comm_lib.CommHandler(
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        streaming=const.Streaming.DISABLE,  # Not supported yet.
    )

    def main(event: dict[str, object], context: _Context) -> _Response:
        try:
            if "http" not in event:
                raise errors.BodyInvalidError('missing "http" key in event')

            http = _EventHTTP.from_raw(event["http"])
            if isinstance(http, Exception):
                raise errors.BodyInvalidError(http)

            if http.headers is None:
                raise errors.BodyInvalidError(
                    'missing "headers" event.http; have you set "web: raw"?'
                )
            if http.queryString is None:
                raise errors.BodyInvalidError(
                    'missing "queryString" event.http; have you set "web: raw"?'
                )

            query_params = urllib.parse.parse_qs(http.queryString)

            # DigitalOcean does not give the full path to the function, so we'll
            # build it by hardcoding the path prefix ("api/v1/web") and
            # concatenating it with the function name. This should be identical
            # to the path, but DigitalOcean may change this in the future (e.g.
            # a new API version).
            #
            # You might be tempted to use event.http.path, but that's actually
            # the relative path after the prefix + function name.
            path = "/api/v1/web" + context.function_name

            request_url = urllib.parse.urljoin(context.api_host, path)

            comm_req = comm_lib.CommRequest(
                body=_to_body_bytes(http.body),
                headers=http.headers,
                public_path=public_path,
                query_params=query_params,
                raw_request={
                    "context": context,
                    "event": event,
                },
                request_url=request_url,
                serve_origin=serve_origin,
                serve_path=serve_path,
            )

            if http.method == "GET":
                return _to_response(
                    handler.get_sync(comm_req),
                )

            if http.method == "POST":
                if http.body is None:
                    raise errors.BodyInvalidError(
                        'missing "body" event.http; have you set "web: raw"?'
                    )

                body = json.loads(http.body)
                if not isinstance(body, dict):
                    raise errors.BodyInvalidError("body must be an object")

                # These are sent as query params but DigitalOcean munges them with the body
                fn_id = _get_first(
                    query_params.get(
                        server_lib.QueryParamKey.FUNCTION_ID.value
                    ),
                )
                step_id = _get_first(
                    query_params.get(server_lib.QueryParamKey.STEP_ID.value),
                )

                if fn_id is None:
                    raise errors.QueryParamMissingError(
                        server_lib.QueryParamKey.FUNCTION_ID.value
                    )
                if step_id is None:
                    raise errors.QueryParamMissingError(
                        server_lib.QueryParamKey.STEP_ID.value
                    )
                call = server_lib.ServerRequest.from_raw(body)
                if isinstance(call, Exception):
                    raise call

                return _to_response(
                    handler.post_sync(comm_req),
                )

            if http.method == "PUT":
                # DigitalOcean does not give the full path to the function, so
                # we'll build it by hardcoding the path prefix ("api/v1/web")
                # and concatenating it with the function name. This should be
                # identical to the path, but DigitalOcean may change this in the
                # future (e.g. a new API version).
                #
                # You might be tempted to use event.http.path, but that's
                # actually the relative path after the prefix + function name.
                path = "/api/v1/web" + context.function_name

                request_url = urllib.parse.urljoin(context.api_host, path)

                return _to_response(
                    handler.put_sync(comm_req),
                )

            raise Exception(f"unsupported method: {http.method}")
        except Exception as e:
            comm_res = comm_lib.CommResponse.from_error(client.logger, e)
            if isinstance(
                e, (errors.BodyInvalidError, errors.QueryParamMissingError)
            ):
                comm_res.status_code = 400

            return _to_response(comm_res)

    return main


def _get_first(
    items: list[types.T] | None,
) -> types.T | None:
    if items is None or len(items) == 0:
        return None
    return items[0]


def _to_body_bytes(body: str | None) -> bytes:
    if body is None:
        return b""
    return body.encode("utf-8")


def _to_response(
    comm_res: comm_lib.CommResponse,
) -> _Response:
    return {
        "body": comm_res.body,  # type: ignore
        "headers": comm_res.headers,
        "statusCode": comm_res.status_code,
    }


class _EventHTTP(types.BaseModel):
    body: str | None = None
    headers: dict[str, str] | None = None
    method: str | None = None
    path: str | None = None
    queryString: str | None = None  # noqa: N815


class _Context(typing.Protocol):
    # E.g. "https://faas-nyc1-2ef2e6cc.doserverless.co"
    api_host: str

    # E.g. "/fn-b094417f/sample/hello"
    function_name: str


class _Response(typing.TypedDict):
    body: str
    headers: dict[str, str]
    statusCode: int
