# ruff: noqa: S603, S607, T201

import os
import pathlib
import subprocess
import threading
import time
import typing

import httpx

from .command_runner import _CommandRunner


class _Server:
    @property
    def origin(self) -> str:
        return f"http://0.0.0.0:{self.port}"

    def __init__(self) -> None:
        port: int
        dev_server_port_env_var = os.getenv("DEV_SERVER_PORT")
        if dev_server_port_env_var:
            port = int(dev_server_port_env_var)
        else:
            port = 8288
        self.port = port

        artifacts_dir = pathlib.Path("artifacts").absolute()
        print(f"Using artifacts directory: {artifacts_dir}")

        # Create artifacts directory if it doesn't exist.
        artifacts_dir.mkdir(exist_ok=True)

        self._runner = _CommandRunner(
            f"npx --yes inngest-cli@latest dev --no-discovery --no-poll --port {self.port}",
            output_path=artifacts_dir / "dev_server.log",
        )

        self._enabled = os.getenv("DEV_SERVER_ENABLED") != "0"
        self._output_thread: typing.Optional[threading.Thread] = None

        self._process: typing.Optional[subprocess.Popen[str]] = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._enabled is False:
            return

        print("Dev Server: starting")

        if self._runner.is_running():
            raise Exception("Dev Server is already running")

        self._runner.run()
        self._wait_for_server()
        self._runner.stop_printing()

    def _wait_for_server(self) -> None:
        print("Dev Server: waiting for start")

        while not self._ready_event.is_set():
            try:
                httpx.get(f"http://127.0.0.1:{self.port}")
                self._ready_event.set()
                break
            except Exception:
                time.sleep(0.1)

        print("Dev Server: started")

    def stop(self) -> None:
        if self._enabled is False:
            return

        print("Dev Server: stopping")

        if not self._runner.is_running():
            raise Exception("Dev Server is not running")

        self._runner.kill()
        print("Dev Server: stopped")


server = _Server()
