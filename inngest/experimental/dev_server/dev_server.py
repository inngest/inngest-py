# ruff: noqa: S603, S607, T201

import os
import subprocess
import threading
import time
import typing

import httpx


class _Server:
    @property
    def origin(self) -> str:
        return f"http://0.0.0.0:{self.port}"

    def __init__(self) -> None:
        self._enabled = os.getenv("DEV_SERVER_ENABLED") != "0"
        # self._output_thread: typing.Optional[threading.Thread] = None

        port: int
        dev_server_port_env_var = os.getenv("DEV_SERVER_PORT")
        if dev_server_port_env_var:
            port = int(dev_server_port_env_var)
        else:
            port = 8288
        self.port = port

        self._process: typing.Optional[subprocess.Popen[str]] = None
        self._ready_event = threading.Event()

    def start(self) -> None:
        if self._enabled is False:
            return

        print("Dev Server: starting")

        if self._process:
            raise Exception("Dev Server is already running")

        self._process = subprocess.Popen(
            [
                "npx",
                "--yes",
                "inngest-cli@latest",
                "dev",
                "--no-discovery",
                "--no-poll",
                "--port",
                f"{self.port}",
            ],
            bufsize=1,
            # stderr=subprocess.STDOUT,
            # stdout=subprocess.PIPE,
            text=True,
            universal_newlines=True,
        )

        self._ready_event.clear()
        # self._output_thread = threading.Thread(target=self._print_output)
        # self._output_thread.start()
        self._wait_for_server()

    def _print_output(self) -> None:
        if self._process is None:
            raise Exception("missing process")
        if self._process.stdout is None:
            raise Exception("missing stdout")

        for line in self._process.stdout:
            if self._ready_event.is_set() is False:
                print(line, end="")

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

        # if self._output_thread is None:
        # raise Exception("missing output thread")
        if self._process is None:
            raise Exception("missing process")

        self._process.terminate()

        # Try to gracefully stop but kill it if that fails.
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)

        # self._output_thread.join()

        print("Dev Server: stopped")


server = _Server()
