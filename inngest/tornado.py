"""Tornado integration for Inngest."""

import json
import typing

import tornado.web

from inngest._internal import (
    client_lib,
    comm_lib,
    config_lib,
    function,
    server_lib,
    transforms,
)

FRAMEWORK = server_lib.Framework.TORNADO


def serve(
    app: tornado.web.Application,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    serve_origin: typing.Optional[str] = None,
    serve_path: typing.Optional[str] = None,
) -> None:
    """
    Serve Inngest functions in a Tornado app.

    Args:
    ----
        app: Tornado app.
        client: Inngest client.
        functions: List of functions to serve.

        serve_origin: Origin to serve the functions from.
        serve_path: Path to serve the functions from.
    """

    serve_path = config_lib.get_serve_path(serve_path)

    handler = comm_lib.CommHandler(
        client=client,
        framework=FRAMEWORK,
        functions=functions,
    )

    class InngestHandler(tornado.web.RequestHandler):
        def data_received(
            self, chunk: bytes
        ) -> typing.Optional[typing.Awaitable[None]]:
            return None

        def get(self) -> None:
            comm_res = handler.get_sync(
                comm_lib.CommRequest(
                    body=self.request.body,
                    headers=dict(self.request.headers.items()),
                    query_params=_parse_query_params(
                        self.request.query_arguments
                    ),
                    raw_request=self.request,
                    request_url=self.request.full_url(),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
            )

            self._write_comm_response(comm_res)

        def post(self) -> None:
            comm_res = handler.post_sync(
                comm_lib.CommRequest(
                    body=self.request.body,
                    headers=dict(self.request.headers.items()),
                    query_params=_parse_query_params(
                        self.request.query_arguments
                    ),
                    raw_request=self.request,
                    request_url=self.request.full_url(),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
            )

            self._write_comm_response(comm_res)

        def put(self) -> None:
            comm_res = handler.put_sync(
                comm_lib.CommRequest(
                    body=self.request.body,
                    headers=dict(self.request.headers.items()),
                    query_params=_parse_query_params(
                        self.request.query_arguments
                    ),
                    raw_request=self.request,
                    request_url=self.request.full_url(),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                )
            )

            self._write_comm_response(comm_res)

        def _write_comm_response(
            self,
            comm_res: comm_lib.CommResponse,
        ) -> None:
            body = transforms.dump_json(comm_res.body)
            if isinstance(body, Exception):
                comm_res = comm_lib.CommResponse.from_error(client.logger, body)
                body = json.dumps(comm_res.body)

            self.write(body)

            for k, v in comm_res.headers.items():
                self.add_header(k, v)

            self.set_status(comm_res.status_code)

    app.add_handlers(r".*", [(serve_path, InngestHandler)])


def _parse_query_params(raw: dict[str, list[bytes]]) -> dict[str, str]:
    return {k: v[0].decode("utf-8") for k, v in raw.items()}
