import os
import unittest

import pytest

from . import client_lib, const, errors, event_lib


class Test(unittest.TestCase):
    def test_dev_env_var(self) -> None:
        """
        No error is raised when the INNGEST_DEV environment variable is set.
        This env var is a fallback for the is_production param.
        """

        os.environ[const.EnvKey.DEV.value] = "1"
        self.addCleanup(lambda: os.environ.pop(const.EnvKey.DEV.value))

        client_lib.Inngest(
            app_id="test",
            signing_key="foo",
        )

    def test_event_key_env_var(self) -> None:
        os.environ[const.EnvKey.EVENT_KEY.value] = "foo2"
        self.addCleanup(lambda: os.environ.pop(const.EnvKey.EVENT_KEY.value))
        client = client_lib.Inngest(
            app_id="test",
            signing_key="foo",
        )
        assert client.event_key == "foo2"

    def test_event_key_param(self) -> None:
        client = client_lib.Inngest(
            app_id="test",
            event_key="foo1",
            signing_key="foo",
        )
        assert client.event_key == "foo1"

    def test_event_key_missing(self) -> None:
        """
        Error is raised when the event key is not set in production.
        """

        client = client_lib.Inngest(
            app_id="test",
            signing_key="foo",
        )

        with pytest.raises(errors.MissingEventKeyError):
            client.send_sync(event_lib.Event(name="foo"))

    def test_signing_key_env_var(self) -> None:
        os.environ[const.EnvKey.SIGNING_KEY.value] = "foo2"
        self.addCleanup(lambda: os.environ.pop(const.EnvKey.SIGNING_KEY.value))
        client = client_lib.Inngest(app_id="test")
        assert client.signing_key == "foo2"

    def test_signing_key_param(self) -> None:
        client = client_lib.Inngest(
            app_id="test",
            signing_key="foo1",
        )
        assert client.signing_key == "foo1"

    def test_signing_key_missing(self) -> None:
        """
        Error is raised when the signing key is not set in production.
        """

        with pytest.raises(errors.MissingSigningKeyError):
            client_lib.Inngest(app_id="test")

    def test_api_base_url_env_var(self) -> None:
        os.environ[const.EnvKey.API_BASE_URL.value] = "example.com"
        self.addCleanup(lambda: os.environ.pop(const.EnvKey.API_BASE_URL.value))
        client = client_lib.Inngest(
            app_id="test",
            signing_key="foo",
        )
        assert client.api_origin == "example.com"

    def test_api_base_url_param(self) -> None:
        client = client_lib.Inngest(
            api_base_url="example.com",
            app_id="test",
            signing_key="foo",
        )
        assert client.api_origin == "example.com"

    def test_api_base_url_default_prod(self) -> None:
        client = client_lib.Inngest(
            app_id="test",
            signing_key="foo",
        )
        assert client.api_origin == "https://api.inngest.com/"

    def test_api_base_url_default_dev(self) -> None:
        client = client_lib.Inngest(
            app_id="test",
            is_production=False,
            signing_key="foo",
        )
        assert client.api_origin == "http://127.0.0.1:8288/"

    def test_event_api_base_url_env_var(self) -> None:
        os.environ[const.EnvKey.EVENT_API_BASE_URL.value] = "example.com"
        self.addCleanup(
            lambda: os.environ.pop(const.EnvKey.EVENT_API_BASE_URL.value)
        )
        client = client_lib.Inngest(
            app_id="test",
            signing_key="foo",
        )
        assert client.event_api_origin == "example.com"

    def test_event_api_base_url_param(self) -> None:
        client = client_lib.Inngest(
            app_id="test",
            event_api_base_url="example.com",
            signing_key="foo",
        )
        assert client.event_api_origin == "example.com"

    def test_eventapi_base_url_default_prod(self) -> None:
        client = client_lib.Inngest(
            app_id="test",
            signing_key="foo",
        )
        assert client.event_api_origin == "https://inn.gs/"

    def test_eventapi_base_url_default_dev(self) -> None:
        client = client_lib.Inngest(
            app_id="test",
            is_production=False,
            signing_key="foo",
        )
        assert client.event_api_origin == "http://127.0.0.1:8288/"
