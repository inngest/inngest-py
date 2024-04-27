import json

import tornado.httpclient
import tornado.ioloop
import tornado.log
import tornado.testing
import tornado.web

import inngest
import inngest.tornado

from . import base, cases

_framework = "tornado"


class TestRegistration(tornado.testing.AsyncHTTPTestCase):
    app: tornado.web.Application = tornado.web.Application()

    def get_app(self) -> tornado.web.Application:
        return self.app

    def register(self, headers: dict[str, str]) -> base.RegistrationResponse:
        res = self.fetch(
            "/api/inngest",
            body=json.dumps({}),
            headers=headers,
            method="PUT",
        )
        return base.RegistrationResponse(
            body=json.loads(res.body),
            status_code=res.code,
        )

    def serve(
        self,
        client: inngest.Inngest,
        fns: list[inngest.Function],
    ) -> None:
        inngest.tornado.serve(
            self.app,
            client,
            fns,
        )


for case in cases.create_cases(_framework):
    test_name = f"test_{case.name}"
    setattr(TestRegistration, test_name, case.run_test)


if __name__ == "__main__":
    tornado.testing.main()
    tornado.testing.main()
