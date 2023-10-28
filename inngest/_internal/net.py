import hashlib
import hmac
from typing import Literal
from urllib.parse import parse_qs, urlparse

from requests import session

from .const import LANGUAGE, VERSION, HeaderKey
from .errors import InvalidRequestSignature, MissingHeader, MissingSigningKey
from .transforms import remove_signing_key_prefix

Method = Literal["GET", "POST"]


requests_session = session()


def create_headers(
    *,
    framework: str | None = None,
) -> dict[str, str]:
    headers = {
        HeaderKey.USER_AGENT.value: f"inngest-{LANGUAGE}:v{VERSION}",
        HeaderKey.SDK.value: f"inngest-{LANGUAGE}:v{VERSION}",
    }

    if framework is not None:
        headers[HeaderKey.FRAMEWORK.value] = framework

    return headers


def parse_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme == "":
        parsed._replace(scheme="https")

    return parsed.geturl()


class RequestSignature:
    _signature: str | None = None
    _timestamp: int | None = None

    def __init__(
        self,
        body: bytes,
        headers: dict[str, str],
        is_production: bool,
    ) -> None:
        self._body = body
        self._is_production = is_production

        sig_header = headers.get(HeaderKey.SIGNATURE.value)
        if sig_header is not None:
            parsed = parse_qs(sig_header)
            if "t" in parsed:
                self._timestamp = int(parsed["t"][0])
            if "s" in parsed:
                self._signature = parsed["s"][0]

    def validate(self, signing_key: str | None) -> None:
        if not self._is_production:
            return

        if signing_key is None:
            raise MissingSigningKey(
                "cannot validate signature in production mode without a signing key"
            )

        if self._signature is None:
            raise MissingHeader(
                f"cannot validate signature in production mode without a {HeaderKey.SIGNATURE.value} header"
            )

        mac = hmac.new(
            remove_signing_key_prefix(signing_key).encode("utf-8"),
            self._body,
            hashlib.sha256,
        )
        mac.update(str(self._timestamp).encode())
        if not hmac.compare_digest(self._signature, mac.hexdigest()):
            raise InvalidRequestSignature()
