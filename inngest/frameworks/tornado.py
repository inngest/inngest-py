import json
from typing import Awaitable

from tornado.web import Application, RequestHandler

from inngest.client import Inngest
from inngest.comm import CommHandler
from inngest.const import HeaderKey
from inngest.errors import MissingParam
from inngest.execution import Call
from inngest.function import Function
from inngest.net import RequestSignature


def serve(
    app: Application,
    client: Inngest,
    functions: list[Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    comm = CommHandler(
        api_origin=base_url or client.base_url,
        client=client,
        framework="flask",
        functions=functions,
        logger=client.logger,
        signing_key=signing_key,
    )

    class InngestHandler(RequestHandler):
        def data_received(self, chunk: bytes) -> Awaitable[None] | None:
            return None

        def post(self) -> None:
            fn_id: str | None
            raw_fn_id = self.request.query_arguments.get("fnId")
            if raw_fn_id is None or len(raw_fn_id) == 0:
                raise MissingParam("fnId")
            fn_id = raw_fn_id[0].decode("utf-8")

            headers: dict[str, str] = {}

            for k, v in self.request.headers.items():
                if isinstance(k, str) and isinstance(v[0], str):
                    headers[k] = v[0]

            comm_res = comm.call_function(
                call=Call.from_dict(json.loads(self.request.body)),
                fn_id=fn_id,
                req_sig=RequestSignature(
                    body=self.request.body,
                    headers=headers,
                ),
            )

            self.write(json.dumps(comm_res.body))

            for k, v in comm_res.headers.items():
                self.add_header(k, v)

            self.set_status(comm_res.status_code)

        def put(self) -> None:
            remote_ip = (
                self.request.headers.get(HeaderKey.REAL_IP.value)
                or self.request.headers.get(HeaderKey.FORWARDED_FOR.value)
                or self.request.remote_ip
            )

            comm_res = comm.register(
                app_url=self.request.full_url(),
                # TODO: Find a better way to figure this out.
                is_from_dev_server=remote_ip == "127.0.0.1",
            )

            self.write(json.dumps(comm_res.body))

            for k, v in comm_res.headers.items():
                self.add_header(k, v)

            self.set_status(comm_res.status_code)

    app.add_handlers(r".*", [("/api/inngest", InngestHandler)])
