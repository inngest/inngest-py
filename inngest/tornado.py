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
)


def serve(
    app: tornado.web.Application,
    client: client_lib.Inngest,
    functions: list[function.FunctionSync],
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

    class InngestHandler(tornado.web.RequestHandler):
        def data_received(self, chunk: bytes) -> typing.Awaitable[None] | None:
            return None

        def post(self) -> None:
            fn_id: str | None
            raw_fn_id = self.request.query_arguments.get("fnId")
            if raw_fn_id is None or len(raw_fn_id) == 0:
                raise errors.MissingParam("fnId")
            fn_id = raw_fn_id[0].decode("utf-8")

            headers: dict[str, str] = {}

            for k, v in self.request.headers.items():
                if isinstance(k, str) and isinstance(v[0], str):
                    headers[k] = v[0]

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
            remote_ip = (
                self.request.headers.get(const.HeaderKey.REAL_IP.value)
                or self.request.headers.get(const.HeaderKey.FORWARDED_FOR.value)
                or self.request.remote_ip
            )

            comm_res = handler.register_sync(
                app_url=self.request.full_url(),
                # TODO: Find a better way to figure this out.
                is_from_dev_server=remote_ip == "127.0.0.1",
            )

            self.write(json.dumps(comm_res.body))

            for k, v in comm_res.headers.items():
                self.add_header(k, v)

            self.set_status(comm_res.status_code)

    app.add_handlers(r".*", [("/api/inngest", InngestHandler)])
