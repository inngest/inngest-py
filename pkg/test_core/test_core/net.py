import socket
import typing

HOST: typing.Final = "0.0.0.0"


def get_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
        assert isinstance(port, int)
        return port
