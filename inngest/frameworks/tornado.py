import json

from tornado.web import Application, RequestHandler

from inngest.client import Inngest
from inngest.comm import CommHandler
from inngest.function import Function
from inngest.execution import Call


def serve(
    app: Application,
    client: Inngest,
    functions: list[Function],
    *,
    base_url: str | None = None,
    signing_key: str | None = None,
) -> None:
    comm = CommHandler(
        api_origin=base_url,
        client=client,
        framework="flask",
        functions=functions,
        logger=client.logger,
        signing_key=signing_key,
    )

    class InngestHandler(RequestHandler):
        def post(self) -> None:
            fn_id: str | None
            raw_fn_id = self.request.query_arguments.get("fnId")
            if raw_fn_id is None or len(raw_fn_id) == 0:
                raise Exception("missing fnId")
            fn_id = raw_fn_id[0].decode("utf-8")

            comm_res = comm.call_function(
                call=Call.from_raw(json.loads(self.request.body)),
                fn_id=fn_id,
            )

            self.write(json.dumps(comm_res.body))

            for k, v in comm_res.headers.items():
                self.add_header(k, v)

            self.set_status(comm_res.status_code)

        def put(self) -> None:
            remote_ip = (
                self.request.headers.get("X-Real-IP")
                or self.request.headers.get("X-Forwarded-For")
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
