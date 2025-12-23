# ruff: noqa: S603, S607, T201

import os
import pathlib
import subprocess
import threading
import time
import typing

import httpx

from .command_runner import _CommandRunner

_dev_server_version: typing.Final = "1.15.0"


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

        log_path: pathlib.Path | None = None
        if os.getenv("DEV_SERVER_LOGS") == "1":
            artifacts_dir = pathlib.Path("artifacts").absolute()
            print(f"Using artifacts directory: {artifacts_dir}")

            # Create artifacts directory if it doesn't exist.
            artifacts_dir.mkdir(exist_ok=True)

            log_path = artifacts_dir / "dev_server.log"

        self._runner = _CommandRunner(
            f"npx --ignore-scripts=false --yes inngest-cli@{_dev_server_version} dev --no-discovery --no-poll --port {self.port}",
            log_path=log_path,
        )

        self._enabled = os.getenv("DEV_SERVER_ENABLED") != "0"
        self._output_thread: threading.Thread | None = None

        self._process: subprocess.Popen[str] | None = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._enabled is False:
            return

        print("Dev Server: starting")

        # Print inngest-cli version
        try:
            result = subprocess.run(
                [
                    "npx",
                    "--ignore-scripts=false",
                    "--yes",
                    f"inngest-cli@{_dev_server_version}",
                    "version",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                print(f"inngest-cli version: {result.stdout.strip()}")
            else:
                print(
                    f"Failed to get inngest-cli version: {result.stderr.strip()}"
                )
        except Exception as e:
            print(f"Error getting inngest-cli version: {e}")

        if self._runner.is_running():
            raise Exception("Dev Server is already running")

        self._runner.run()
        self._wait_for_server()
        self._runner.stop_printing()

    def _wait_for_server(self) -> None:
        print("Dev Server: waiting for start")

        while not self._ready_event.is_set():
            try:
                res = httpx.post(
                    f"http://127.0.0.1:{self.port}/v0/connect/start"
                )
                if res.status_code == 200:
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
