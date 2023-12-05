import hashlib
import hmac
import os
import typing
import urllib.parse

from . import const, errors, transforms, types

Method = typing.Literal["GET", "POST"]


def create_headers(
    framework: const.Framework | None,
    server_kind: const.ServerKind | None,
) -> dict[str, str]:
    """
    Create standard headers that should exist on every possible outgoing
    request.
    """

    headers = {
        const.HeaderKey.CONTENT_TYPE.value: "application/json",
        const.HeaderKey.SDK.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
        const.HeaderKey.USER_AGENT.value: f"inngest-{const.LANGUAGE}:v{const.VERSION}",
    }

    if framework is not None:
        headers[const.HeaderKey.FRAMEWORK.value] = framework.value
    if server_kind is not None:
        headers[const.HeaderKey.EXPECTED_SERVER_KIND.value] = server_kind.value

    return headers


def create_serve_url(
    *,
    request_url: str,
    serve_origin: str | None,
    serve_path: str | None,
) -> str:
    """
    Create the serve URL, which is the URL that the Executor will use to reach
    the SDK.

    Args:
    ----
        request_url: The URL that the Executor is using to reach the SDK.
        serve_origin: User-specified override for the serve origin.
        serve_path: User-specified override for the serve path.
    """

    # User can also specify these via env vars. The env vars take precedence.
    serve_origin = os.getenv(const.EnvKey.SERVE_ORIGIN.value, serve_origin)
    serve_path = os.getenv(const.EnvKey.SERVE_PATH.value, serve_path)

    parsed_url = urllib.parse.urlparse(request_url)
    new_scheme = parsed_url.scheme
    new_netloc = parsed_url.netloc
    new_path = parsed_url.path

    if serve_origin is not None:
        has_scheme = "://" in serve_origin
        if has_scheme:
            parsed_origin = urllib.parse.urlparse(serve_origin)
            new_scheme = parsed_origin.scheme or new_scheme
            new_netloc = parsed_origin.netloc or new_netloc
        else:
            new_scheme = "https"
            new_netloc = serve_origin

    if serve_path is not None:
        new_path = serve_path

    return urllib.parse.urlunparse(
        (new_scheme, new_netloc, new_path, "", "", "")
    )


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Ensure that known headers are in the correct casing.
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

    def validate(self, signing_key: str | None) -> types.MaybeError[None]:
        if not self._is_production:
            return None

        if signing_key is None:
            return errors.MissingSigningKeyError(
                "cannot validate signature in production mode without a signing key"
            )

        if self._signature is None:
            return errors.MissingHeaderError(
                f"cannot validate signature in production mode without a {const.HeaderKey.SIGNATURE.value} header"
            )

        mac = hmac.new(
            transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
            self._body,
            hashlib.sha256,
        )
        mac.update(str(self._timestamp).encode("utf-8"))
        if not hmac.compare_digest(self._signature, mac.hexdigest()):
            return errors.InvalidRequestSignatureError()

        return None
