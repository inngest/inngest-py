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


def serve(
    app: tornado.web.Application,
    client: client_lib.Inngest,
    functions: list[function.Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    handler = comm.CommHandler(
        base_url=base_url or client.base_url,
        client=client,
        framework=const.Framework.TORNADO,
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
            self.write(json.dumps(comm_res.body))
            for k, v in comm_res.headers.items():
                self.add_header(k, v)
            self.set_status(comm_res.status_code)

        def post(self) -> None:
            fn_id: str | None
            raw_fn_id = self.request.query_arguments.get("fnId")
            if raw_fn_id is None or len(raw_fn_id) == 0:
                raise errors.MissingParam("fnId")
            fn_id = raw_fn_id[0].decode("utf-8")

            headers = net.normalize_headers(dict(self.request.headers.items()))

            comm_res = handler.call_function_sync(
                call=execution.Call.from_dict(json.loads(self.request.body)),
                fn_id=fn_id,
                req_sig=net.RequestSignature(
                    body=self.request.body,
                    headers=headers,
                    is_production=client.is_production,
                ),
            )
            self.write(json.dumps(comm_res.body))
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
            self.write(json.dumps(comm_res.body))
            for k, v in comm_res.headers.items():
                self.add_header(k, v)
            self.set_status(comm_res.status_code)

    app.add_handlers(r".*", [("/api/inngest", InngestHandler)])
