"""
TODO: Figure out how to also test inngest.django.serve with async_mode=True. We
ran into some "Settings already configured" errors when we had separate files
for async and sync, likely due to django.conf.settings being a singleton.
"""

import threading
import unittest

import django.conf
import django.test

import inngest
import inngest.django

from . import base, cases, dev_server, http_proxy, net


class SetupState:
    is_setup = False
    is_torn_down = False
    mutex = threading.Lock()


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
    client: inngest.Inngest
    django_client: django.test.Client
    proxy: http_proxy.Proxy

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.client = inngest_client
        cls.django_client = django.test.Client()
        cls.proxy = http_proxy.Proxy(cls.on_proxy_request).start()
        base.register(cls.proxy.port)

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        cls.proxy.stop()

    @classmethod
    def on_proxy_request(
        cls,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> http_proxy.Response:
        new_headers = {key: value[0] for key, value in headers.items()}

        res = cls.django_client.generic(
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
