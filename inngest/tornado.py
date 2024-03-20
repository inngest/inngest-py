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
    handler = comm.CommHandler(
        api_base_url=client.api_origin,
        client=client,
        framework=FRAMEWORK,
        functions=functions,
        signing_key=client.signing_key,
    )

    class InngestHandler(tornado.web.RequestHandler):
        def data_received(
            self, chunk: bytes
        ) -> typing.Optional[typing.Awaitable[None]]:
            return None

        def get(self) -> None:
            headers = net.normalize_headers(dict(self.request.headers.items()))

            server_kind = transforms.get_server_kind(headers)
            if isinstance(server_kind, Exception):
                client.logger.error(server_kind)
                server_kind = None

            comm_res = handler.inspect(server_kind)

            self._write_comm_response(comm_res, server_kind)

        def post(self) -> None:
            fn_id: typing.Optional[str]
            raw_fn_id = self.request.query_arguments.get(
                const.QueryParamKey.FUNCTION_ID.value
            )
            if raw_fn_id is None or len(raw_fn_id) == 0:
                raise errors.QueryParamMissingError(
                    const.QueryParamKey.FUNCTION_ID.value
                )
            fn_id = raw_fn_id[0].decode("utf-8")

            step_id: typing.Optional[str]
            raw_step_id = self.request.query_arguments.get(
                const.QueryParamKey.STEP_ID.value
            )
            if raw_step_id is None or len(raw_step_id) == 0:
                raise errors.QueryParamMissingError(
                    const.QueryParamKey.STEP_ID.value
                )
            step_id = raw_step_id[0].decode("utf-8")

            headers = net.normalize_headers(dict(self.request.headers.items()))

            server_kind = transforms.get_server_kind(headers)
            if isinstance(server_kind, Exception):
                client.logger.error(server_kind)
                server_kind = None

            call = execution.Call.from_raw(json.loads(self.request.body))
            if isinstance(call, Exception):
                return self._write_comm_response(
                    comm.CommResponse.from_error(client.logger, call),
                    server_kind,
                )

            comm_res = handler.call_function_sync(
                call=call,
                fn_id=fn_id,
                req_sig=net.RequestSignature(
                    body=self.request.body,
                    headers=headers,
                    mode=client._mode,
                ),
                target_hashed_id=step_id,
            )

            self._write_comm_response(comm_res, server_kind)

        def put(self) -> None:
            headers = net.normalize_headers(dict(self.request.headers.items()))

            server_kind = transforms.get_server_kind(headers)
            if isinstance(server_kind, Exception):
                client.logger.error(server_kind)
                server_kind = None

            sync_id: typing.Optional[str] = None
            raw_sync_id = self.request.query_arguments.get(
                const.QueryParamKey.SYNC_ID.value
            )
            if raw_sync_id is not None:
                sync_id = raw_sync_id[0].decode("utf-8")

            comm_res = handler.register_sync(
                app_url=net.create_serve_url(
                    request_url=self.request.full_url(),
                    serve_origin=serve_origin,
                    serve_path=serve_path,
                ),
                server_kind=server_kind,
                sync_id=sync_id,
            )

            self._write_comm_response(comm_res, server_kind)

        def _write_comm_response(
            self,
            comm_res: comm.CommResponse,
            server_kind: typing.Optional[const.ServerKind],
        ) -> None:
            body = transforms.dump_json(comm_res.body)
            if isinstance(body, Exception):
                comm_res = comm.CommResponse.from_error(client.logger, body)
                body = json.dumps(comm_res.body)

            self.write(body)

            for k, v in comm_res.headers.items():
                self.add_header(k, v)
            for k, v in net.create_headers(
                env=client.env,
                framework=FRAMEWORK,
                server_kind=server_kind,
                signing_key=None,
            ).items():
                self.add_header(k, v)

            self.set_status(comm_res.status_code)

    app.add_handlers(r".*", [("/api/inngest", InngestHandler)])
