import hashlib
import hmac
import random
import socket
import time
import typing
import urllib.parse

from inngest._internal import errors, server_lib, transforms

HOST: typing.Final = "0.0.0.0"

_used_ports: set[int] = set()


def sign_request(
    body: bytes,
    signing_key: str,
    unix_ms: typing.Optional[int] = None,
) -> str:
    """
    Sign a request to the SDK. This mimics the request signing mechanism in an
    Inngest Server.
    """

    if unix_ms is None:
        unix_ms = round(time.time())

    canonicalized = transforms.canonicalize(body)
    if isinstance(canonicalized, Exception):
        raise canonicalized

    mac = hmac.new(
        transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
        canonicalized,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    sig = mac.hexdigest()

    return f"t={unix_ms}&s={sig}"


def validate_response(
    *,
    body: bytes,
    headers: dict[str, str],
    signing_key: str,
) -> None:
    """
    Validate a response from the SDK. This mimics the response signature
    validation mechanism in an Inngest Server.
    """

    timestamp = None
    signature = None
    sig_header = headers.get(server_lib.HeaderKey.SIGNATURE.value)
    if sig_header is None:
        raise errors.HeaderMissingError(
            f"cannot validate signature in production mode without a {server_lib.HeaderKey.SIGNATURE.value} header"
        )
    else:
        parsed = urllib.parse.parse_qs(sig_header)
        if "t" in parsed:
            timestamp = int(parsed["t"][0])
        if "s" in parsed:
            signature = parsed["s"][0]

    if signature is None:
        raise Exception(
            f"{server_lib.HeaderKey.SIGNATURE.value} header is malformed"
        )

    mac = hmac.new(
        transforms.remove_signing_key_prefix(signing_key).encode("utf-8"),
        body,
        hashlib.sha256,
    )

    if timestamp:
        mac.update(str(timestamp).encode("utf-8"))

    if not hmac.compare_digest(signature, mac.hexdigest()):
        raise errors.SigVerificationFailedError()


def get_available_port() -> int:
    start_time = time.time()

    while True:
        if time.time() - start_time > 5:
            raise Exception("timeout finding available port")

        port = random.randint(9000, 9999)

        if port in _used_ports:
            continue

        if not _is_port_available(port):
            continue

        _used_ports.add(port)
        return port


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False
