import os
import signal
import subprocess
import threading

from .net import get_available_port

_DEFAULT_DEV_SERVER_PORT = 8288

_enabled = os.getenv("DEV_SERVER_ENABLED") != "0"

DEV_SERVER_PORT: int
dev_server_port_env_var = os.getenv("DEV_SERVER_PORT")
if dev_server_port_env_var:
    DEV_SERVER_PORT = int(dev_server_port_env_var)
elif _enabled:
    DEV_SERVER_PORT = get_available_port()
else:
    DEV_SERVER_PORT = _DEFAULT_DEV_SERVER_PORT


class _DevServer:
    _process: subprocess.Popen[bytes] | None = None
    _thread: threading.Thread | None = None

    def __init__(
        self,
        *,
        enabled: bool,
        port: int,
        verbose: bool,
    ) -> None:
        self._enabled = enabled
        self.port = port
        self._verbose = verbose

    def start(self) -> None:
        if not self._enabled:
            return

        stderr: int | None = subprocess.DEVNULL
        stdout: int | None = subprocess.DEVNULL
        if self._verbose:
            stderr = None
            stdout = None

        def _run() -> None:
            self._process = subprocess.Popen(  # pylint: disable=consider-using-with
                [
                    "npx",
                    "inngest-cli@latest",
                    "dev",
                    "--no-discovery",
                    "--no-poll",
                    "--port",
                    f"{DEV_SERVER_PORT}",
                ],
                stderr=stderr,
                stdout=stdout,
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


dev_server = _DevServer(
    enabled=_enabled,
    port=DEV_SERVER_PORT,
    verbose=os.getenv("DEV_SERVER_VERBOSE") == "1",
)
