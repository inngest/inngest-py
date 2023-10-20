from typing import Literal
from urllib.parse import urlparse

from requests import session

from .const import LANGUAGE, VERSION

Method = Literal["GET", "POST"]


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


requests_session = session()
