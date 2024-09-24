import os
import signal
import subprocess
import threading
import time
import typing

import httpx

from inngest._internal import transforms

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


origin: typing.Final = f"http://{net.HOST}:{PORT}"
event_key: typing.Final = "VouXNGcCBtu2ZKjX3VgErAQlpAFSfpjPOV9m_qqTIZaTNSraIQv144QboQbq9F9Vg8dnULcPl1HXu0Quwi_Yuh"
signing_key: typing.Final = "signkey-prod-3dc05ca0a463ecd5530c9ecc0872f6da31286a5031c3477845791cba941cde77"


class _DevServer:
    _process: typing.Optional[subprocess.Popen[bytes]] = None
    _thread: typing.Optional[threading.Thread] = None

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

        # Delete this when Inngest Lite adds a "disable persistence" option
        res = subprocess.run(["rm", "-rf", ".inngest"], check=True)
        if res.returncode != 0:
            print(f"Failed to delete .inngest directory: {res.stderr}")

        stderr: typing.Optional[int] = subprocess.DEVNULL
        stdout: typing.Optional[int] = subprocess.DEVNULL
        if self._verbose:
            stderr = None
            stdout = None

        def _run() -> None:
            self._process = subprocess.Popen(
                [
                    "npx",
                    "--yes",
                    "inngest-cli@latest",
                    "start",
                    "--event-key",
                    event_key,
                    "--port",
                    f"{PORT}",
                    "--signing-key",
                    transforms.remove_signing_key_prefix(signing_key),
                ],
                stderr=stderr,
                stdout=stdout,
            )

        self._thread = threading.Thread(target=_run)
        self._thread.start()

        print("Waiting for Dev Server to start")
        start_time = time.time()
        while True:
            if time.time() - start_time > 30:
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
