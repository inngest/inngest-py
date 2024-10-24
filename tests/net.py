import contextlib
import socket
import typing

HOST: typing.Final = "0.0.0.0"
_min_port: typing.Final = 9000
_max_port: typing.Final = 9999


def get_available_port() -> int:
    for port in range(_min_port, _max_port + 1):
        with contextlib.closing(
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ) as sock:
            try:
                sock.bind((HOST, port))
                return port
            except OSError:
                continue

    raise Exception("failed to find available port")
