import random
import socket
import time
from typing import Final


HOST: Final = "0.0.0.0"


def get_available_port() -> int:
    start_time = time.time()

    while True:
        if time.time() - start_time > 5:
            raise Exception("timeout finding available port")

        port = random.randint(9000, 9999)
        if _is_port_available(port):
            return port


def _is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
            return True
        except socket.error:
            return False
