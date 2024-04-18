import hashlib
import hmac
import random
import socket
import time
import typing

HOST: typing.Final = "0.0.0.0"

_used_ports: set[int] = set()


def create_signature(body: bytes, signing_key: str, unix_ms: int) -> str:
    mac = hmac.new(
        signing_key.encode("utf-8"),
        body,
        hashlib.sha256,
    )
    mac.update(str(unix_ms).encode("utf-8"))
    sig = mac.hexdigest()
    return f"s={sig}&t={unix_ms}"


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
