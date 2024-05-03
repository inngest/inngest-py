"""
DigitalOcean integration for Inngest
"""

from __future__ import annotations

import json
import typing
import urllib.parse

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

FRAMEWORK = const.Framework.DIGITAL_OCEAN


def serve(
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    serve_origin: typing.Optional[str] = None,
    serve_path: typing.Optional[str] = None,
) -> typing.Callable[[dict[str, object], _Context], _Response]:
    """
    Serve Inngest functions in a DigitalOcean Function.

    Args:
    ----
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
    )

    def main(event: dict[str, object], context: _Context) -> _Response:
        server_kind: typing.Optional[const.ServerKind] = None

        try:
            if not isinstance(event, dict) and "http" not in event:
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

            headers = net.normalize_headers(http.headers)

            _server_kind = transforms.get_server_kind(headers)
            if not isinstance(_server_kind, Exception):
                server_kind = _server_kind
            else:
                client.logger.error(_server_kind)
                server_kind = None

            req_sig = net.RequestSignature(
                body=_to_body_bytes(http.body),
                headers=headers,
                mode=client._mode,
            )

            query_params = urllib.parse.parse_qs(http.queryString)

            if http.method == "GET":
                return _to_response(
                    client,
                    handler.inspect(server_kind, req_sig),
                    server_kind,
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
                    query_params.get(const.QueryParamKey.FUNCTION_ID.value),
                )
                step_id = _get_first(
                    query_params.get(const.QueryParamKey.STEP_ID.value),
                )

                if fn_id is None:
                    raise errors.QueryParamMissingError(
                        const.QueryParamKey.FUNCTION_ID.value
                    )
                if step_id is None:
                    raise errors.QueryParamMissingError(
                        const.QueryParamKey.STEP_ID.value
                    )
                call = execution.Call.from_raw(body)
                if isinstance(call, Exception):
                    raise call

                return _to_response(
                    client,
                    handler.call_function_sync(
                        call=call,
                        fn_id=fn_id,
                        req_sig=req_sig,
                        target_hashed_id=step_id,
                    ),
                    server_kind,
                )

            if http.method == "PUT":
                request_url = urllib.parse.urljoin(
                    context.api_host, http.path or ""
                )
                sync_id = _get_first(
                    query_params.get(const.QueryParamKey.SYNC_ID.value),
                )

                return _to_response(
                    client,
                    handler.register_sync(
                        app_url=net.create_serve_url(
                            request_url=request_url,
                            serve_origin=serve_origin,
                            serve_path=serve_path,
                        ),
                        server_kind=server_kind,
                        sync_id=sync_id,
                    ),
                    server_kind,
                )

            raise Exception(f"unsupported method: {http.method}")
        except Exception as e:
            comm_res = comm.CommResponse.from_error(client.logger, e)
            if isinstance(
                e, (errors.BodyInvalidError, errors.QueryParamMissingError)
            ):
                comm_res.status_code = 400

            return _to_response(
                client,
                comm_res,
                server_kind,
            )

    return main


def _get_first(
    items: typing.Optional[list[types.T]],
) -> typing.Optional[types.T]:
    if items is None or len(items) == 0:
        return None
    return items[0]


def _to_body_bytes(body: typing.Optional[str]) -> bytes:
    if body is None:
        return b""
    return body.encode("utf-8")


def _to_response(
    client: client_lib.Inngest,
    comm_res: comm.CommResponse,
    server_kind: typing.Union[const.ServerKind, None],
) -> _Response:
    return {
        "body": comm_res.body,  # type: ignore
        "headers": {
            **comm_res.headers,
            **net.create_headers(
                env=client.env,
                framework=FRAMEWORK,
                server_kind=server_kind,
            ),
        },
        "statusCode": comm_res.status_code,
    }


class _EventHTTP(types.BaseModel):
    body: typing.Optional[str] = None
    headers: typing.Optional[dict[str, str]] = None
    method: typing.Optional[str] = None
    path: typing.Optional[str] = None
    queryString: typing.Optional[str] = None  # noqa: N815


class _Context(typing.Protocol):
    api_host: str


class _Response(typing.TypedDict):
    body: str
    headers: dict[str, str]
    statusCode: int
