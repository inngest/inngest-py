import os
import signal
import subprocess
import threading

from .net import get_available_port

_DEFAULT_DEV_SERVER_PORT = 8288

_enabled = os.getenv("DEV_SERVER_ENABLED") != "0"

dev_server_port: int
dev_server_port_env_var = os.getenv("DEV_SERVER_PORT")
if dev_server_port_env_var:
    dev_server_port = int(dev_server_port_env_var)
elif _enabled:
    dev_server_port = get_available_port()
else:
    dev_server_port = _DEFAULT_DEV_SERVER_PORT


class _DevServer:
    _process: subprocess.Popen | None = None
    _thread: threading.Thread | None = None

    def __init__(self) -> None:
        self._enabled = os.getenv("DEV_SERVER_ENABLED") != "0"

    def start(self) -> None:
        if not self._enabled:
            return

        def _run() -> None:
            self._process = subprocess.Popen(
                [
                    "npx",
                    "inngest-cli@latest",
                    "dev",
                    "--no-discovery",
                    "--no-poll",
                    "--port",
                    f"{dev_server_port}",
                ],
            )
            self._process.communicate()

        self._thread = threading.Thread(target=_run)
        self._thread.start()
        self._thread.join(timeout=10)

    def stop(self) -> None:
        if not self._enabled:
            return

        if self._process is None:
            raise Exception("missing process")
        if self._thread is None:
            raise Exception("missing thread")

        if not self._thread.is_alive():
            raise Exception("thread is not alive")

        # Would rather use `self._process.terminate()` but sometimes Dev Server
        # takes too long to shutdown.
        os.kill(self._process.pid, signal.SIGKILL)


dev_server = _DevServer()
