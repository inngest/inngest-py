import os
import signal
import subprocess
import threading
import time

import httpx

from . import net

_DEFAULT_DEV_SERVER_PORT = 8288

_enabled = os.getenv("DEV_SERVER_ENABLED") != "0"

PORT: int
dev_server_port_env_var = os.getenv("DEV_SERVER_PORT")
if dev_server_port_env_var:
    PORT = int(dev_server_port_env_var)
elif _enabled:
    PORT = net.get_available_port()
else:
    PORT = _DEFAULT_DEV_SERVER_PORT


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
        print("Starting Dev Server")

        stderr: int | None = subprocess.DEVNULL
        stdout: int | None = subprocess.DEVNULL
        if self._verbose:
            stderr = None
            stdout = None

        def _run() -> None:
            self._process = subprocess.Popen(
                [
                    "npx",
                    "--yes",
                    "inngest-cli@latest",
                    "dev",
                    "--no-discovery",
                    "--no-poll",
                    "--port",
                    f"{PORT}",
                ],
                stderr=stderr,
                stdout=stdout,
            )

        self._thread = threading.Thread(target=_run)
        self._thread.start()

        print("Waiting for Dev Server to start")
        start_time = time.time()
        while True:
            if time.time() - start_time > 20:
                raise Exception("timeout waiting for dev server to start")

            try:
                httpx.get(f"http://127.0.0.1:{self.port}")
                break
            except Exception:
                pass

    def stop(self) -> None:
        if not self._enabled:
            return
        print("Stopping Dev Server")

        if self._process is None:
            raise Exception("missing process")

        self._process.send_signal(signal.SIGINT)

        # Try to gracefully stop but kill it if that fails.
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)


singleton = _DevServer(
    enabled=_enabled,
    port=PORT,
    verbose=os.getenv("DEV_SERVER_VERBOSE") == "1",
)
