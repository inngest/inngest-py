import http.client
import json
from types import TracebackType
from typing import Literal, Type
from urllib.parse import urlparse

from .const import LANGUAGE, VERSION

Method = Literal["GET", "POST"]


class _Request:
    def __init__(
        self,
        *,
        body: object,
        headers: dict[str, str],
        method: Method,
        url: str,
    ):
        parsed_url = urlparse(url)

        if parsed_url.scheme == "http":
            self._conn = http.client.HTTPConnection(parsed_url.netloc)
        else:
            self._conn = http.client.HTTPSConnection(parsed_url.netloc)

        self._body = body
        self._headers = headers
        self._method = method
        self._path = parsed_url.path

    def __enter__(self) -> http.client.HTTPResponse:
        self._conn.request(
            "POST",
            self._path,
            body=json.dumps(self._body),
            headers=self._headers,
        )
        return self._conn.getresponse()

    def __exit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ):
        self._conn.close()


class Fetch:
    @staticmethod
    def post(url: str, body: object, headers: dict[str, str] | None = None) -> _Request:
        return _Request(
            body=body,
            headers=headers or {},
            method="POST",
            url=url,
        )


def create_headers(
    *,
    framework: str | None = None,
) -> dict[str, str]:
    headers = {
        "User-Agent": f"inngest-{LANGUAGE}:v{VERSION}",
        "x-inngest-sdk": f"inngest-{LANGUAGE}:v{VERSION}",
    }

    if framework is not None:
        headers["x-inngest-framework"] = framework

    return headers


def parse_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme == "":
        parsed._replace(scheme="https")

    return parsed.geturl()
