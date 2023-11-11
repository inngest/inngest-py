"""Tornado integration for Inngest."""

import json
import typing

import tornado.web

from inngest._internal import (
    client_lib,
    comm,
    const,
    errors,
    execution,
    function,
    net,
    transforms,
)

FRAMEWORK = const.Framework.TORNADO


def serve(
    app: tornado.web.Application,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    """
    Serve Inngest functions in a Tornado app.

    Args:
    ----
        app: Tornado app.
        client: Inngest client.
        functions: List of functions to serve.

        base_url: Base URL to serve from.
        signing_key: Inngest signing key.
    """
    handler = comm.CommHandler(
        base_url=base_url or client.base_url,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        signing_key=signing_key,
    )

    class InngestHandler(tornado.web.RequestHandler):
        def data_received(self, chunk: bytes) -> typing.Awaitable[None] | None:
            return None

        def get(self) -> None:
            headers = net.normalize_headers(dict(self.request.headers.items()))

            server_kind = transforms.get_server_kind(headers)
            if isinstance(server_kind, Exception):
                client.logger.error(server_kind)
                server_kind = None

            comm_res = handler.inspect(server_kind)

            body = transforms.dump_json(comm_res.body)
            if isinstance(body, Exception):
                comm_res = comm.CommResponse.from_error(
                    client.logger,
                    FRAMEWORK,
                    body,
                )
                body = json.dumps(comm_res.body)

            self.write(body)
            for k, v in comm_res.headers.items():
                self.add_header(k, v)
            self.set_status(comm_res.status_code)

        def post(self) -> None:
            fn_id: str | None
            raw_fn_id = self.request.query_arguments.get(
                const.QueryParamKey.FUNCTION_ID.value
            )
            if raw_fn_id is None or len(raw_fn_id) == 0:
                raise errors.MissingParamError(
                    const.QueryParamKey.FUNCTION_ID.value
                )
            fn_id = raw_fn_id[0].decode("utf-8")

            step_id: str | None
            raw_step_id = self.request.query_arguments.get(
                const.QueryParamKey.STEP_ID.value
            )
            if raw_step_id is None or len(raw_step_id) == 0:
                raise errors.MissingParamError(
                    const.QueryParamKey.STEP_ID.value
                )
            step_id = raw_step_id[0].decode("utf-8")

            headers = net.normalize_headers(dict(self.request.headers.items()))

            comm_res = handler.call_function_sync(
                call=execution.Call.from_dict(json.loads(self.request.body)),
                fn_id=fn_id,
                req_sig=net.RequestSignature(
                    body=self.request.body,
                    headers=headers,
                    is_production=client.is_production,
                ),
                target_hashed_id=step_id,
            )

            body = transforms.dump_json(comm_res.body)
            if isinstance(body, Exception):
                comm_res = comm.CommResponse.from_error(
                    client.logger,
                    FRAMEWORK,
                    body,
                )
                body = json.dumps(comm_res.body)

            self.write(body)
            for k, v in comm_res.headers.items():
                self.add_header(k, v)
            self.set_status(comm_res.status_code)

        def put(self) -> None:
            headers = net.normalize_headers(dict(self.request.headers.items()))

            server_kind = transforms.get_server_kind(headers)
            if isinstance(server_kind, Exception):
                client.logger.error(server_kind)
                server_kind = None

            comm_res = handler.register_sync(
                app_url=self.request.full_url(),
                server_kind=server_kind,
            )

            body = transforms.dump_json(comm_res.body)
            if isinstance(body, Exception):
                comm_res = comm.CommResponse.from_error(
                    client.logger,
                    FRAMEWORK,
                    body,
                )
                body = json.dumps(comm_res.body)

            self.write(body)
            for k, v in comm_res.headers.items():
                self.add_header(k, v)
            self.set_status(comm_res.status_code)

    app.add_handlers(r".*", [("/api/inngest", InngestHandler)])
