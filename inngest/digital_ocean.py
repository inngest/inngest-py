"""Flask integration for Inngest."""

from __future__ import annotations

import http
import json
import typing

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


class _EventHTTP(types.BaseModel):
    headers: typing.Optional[dict[str, str]] = None
    method: typing.Optional[str] = None
    path: typing.Optional[str] = None


class _Context(typing.Protocol):
    api_host: str


class _Response(typing.TypedDict):
    body: str
    headers: dict[str, str]
    status_code: int


def serve(
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    serve_origin: typing.Optional[str] = None,
    serve_path: typing.Optional[str] = None,
) -> typing.Callable[[dict[str, object], _Context], _Response]:
    """
    Serve Inngest functions in a Flask app.

    Args:
    ----
        app: Flask app.
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
        body: dict[str, object] = {}
        event_http = _EventHTTP()
        if isinstance(event, dict):
            body = {
                k: v
                for k, v in event.items()
                if k not in ["http"]
                and isinstance(k, str)
                and not k.startswith("__")
            }

            if "http" in event:
                event_http = _EventHTTP.model_validate(event["http"])

        headers = net.normalize_headers(event_http.headers or {})

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            client.logger.error(server_kind)
            server_kind = None

        req_sig = net.RequestSignature(
            body=json.dumps(body).encode("utf-8"),
            headers=headers,
            mode=client._mode,
        )

        if event_http.method == "GET":
            return _to_response(
                client,
                handler.inspect(server_kind, req_sig),
                server_kind,
            )

        if event_http.method == "POST":
            # These are sent as query params but DigitalOcean munges them with the body
            fn_id = body.get(const.QueryParamKey.FUNCTION_ID.value)
            step_id = body.get(const.QueryParamKey.STEP_ID.value)

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
                return _to_response(
                    client,
                    comm.CommResponse.from_error(client.logger, call),
                    server_kind,
                )

            return _to_response(
                client,
                handler.call_function_sync(
                    call=call,
                    fn_id=str(fn_id),
                    req_sig=req_sig,
                    target_hashed_id=str(step_id),
                ),
                server_kind,
            )

        if event_http.method == "PUT":
            request_url = context.api_host + (event_http.path or "")
            sync_id = body.get(const.QueryParamKey.SYNC_ID.value)

            return _to_response(
                client,
                handler.register_sync(
                    app_url=net.create_serve_url(
                        request_url=request_url,
                        serve_origin=serve_origin,
                        serve_path=serve_path,
                    ),
                    server_kind=server_kind,
                    sync_id=str(sync_id) if sync_id else None,
                ),
                server_kind,
            )

        return {
            "body": f"Method not allowed: {event_http.method}",
            "headers": {
                **net.create_headers(
                    env=client.env,
                    framework=FRAMEWORK,
                    server_kind=server_kind,
                ),
                const.HeaderKey.CONTENT_TYPE.value: "text/plain",
            },
            "status_code": http.HTTPStatus.METHOD_NOT_ALLOWED.value,
        }

    return main


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
        "status_code": comm_res.status_code,
    }
