"""
TODO: Figure out how to also test inngest.django.serve with async_mode=True. We
ran into some "Settings already configured" errors when we had separate files
for async and sync, likely due to django.conf.settings being a singleton.
"""

import unittest

import django.conf
import django.test

import inngest
import inngest.django

from . import base, cases, dev_server, http_proxy, net

_cases = cases.create_cases_sync("django")


django.conf.settings.configure(
    ALLOWED_HOSTS=["*"],
    DEBUG=True,
    ROOT_URLCONF=__name__,
    SECRET_KEY="fake",
)

dev_server_origin = f"http://{net.HOST}:{dev_server.PORT}"

inngest_client = inngest.Inngest(
    app_id="django",
    event_api_base_url=dev_server_origin,
)

# Magic export required by Django
urlpatterns = [
    inngest.django.serve(
        inngest_client,
        [case.fn for case in _cases],
        api_base_url=dev_server_origin,
    ),
]


class TestDjango(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = inngest_client
        self.django_client = django.test.Client()
        self.proxy = http_proxy.Proxy(self.on_proxy_request).start()
        base.register(self.proxy.port)

    def tearDown(self) -> None:
        super().tearDown()
        self.proxy.stop()

    def on_proxy_request(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        new_headers = {key: value[0] for key, value in headers.items()}

        res = self.django_client.generic(
            method=method,
            path=path,
            headers=new_headers,  # type: ignore
            data=body,
        )

        return http_proxy.Response(
            body=res.content,  # type: ignore
            headers=dict(res.headers),
            status_code=res.status_code,  # type: ignore
        )


for case in _cases:
    test_name = f"test_{case.name}"
    setattr(TestDjango, test_name, case.run_test)
