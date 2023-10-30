import hashlib
import hmac
import typing
import urllib.parse

from . import const, errors, transforms

Method = typing.Literal["GET", "POST"]


def create_headers(
    *,
    framework: str | None = None,
) -> dict[str, str]:
    headers = {
        const.HeaderKey.USER_AGENT.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
        const.HeaderKey.SDK.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
    }

    if framework is not None:
        headers[const.HeaderKey.FRAMEWORK.value] = framework

    return headers


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Ensures that known headers are in the correct casing.
    """

    new_headers = {}

    for k, v in headers.items():
        for header_key in const.HeaderKey:
            if k.lower() == header_key.value.lower():
                k = header_key.value

        new_headers[k] = v

    return new_headers


def parse_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)

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

        sig_header = headers.get(const.HeaderKey.SIGNATURE.value)
        if sig_header is not None:
            parsed = urllib.parse.parse_qs(sig_header)
            if "t" in parsed:
                self._timestamp = int(parsed["t"][0])
            if "s" in parsed:
                self._signature = parsed["s"][0]

    def validate(self, signing_key: str | None) -> None:
        if not self._is_production:
            return

        if signing_key is None:
            raise errors.MissingSigningKey(
                "cannot validate signature in production mode without a signing key"
            )

        if self._signature is None:
            raise errors.MissingHeader(
                f"cannot validate signature in production mode without a {const.HeaderKey.SIGNATURE.value} header"
            )

        mac = hmac.new(
            transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
            self._body,
            hashlib.sha256,
        )
        mac.update(str(self._timestamp).encode("utf-8"))
        if not hmac.compare_digest(self._signature, mac.hexdigest()):
            raise errors.InvalidRequestSignature()
