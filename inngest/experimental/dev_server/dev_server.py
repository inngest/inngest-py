# ruff: noqa: S110, S603, S607, T201

import os
import queue
import signal
import subprocess
import sys
import threading
import time
import typing

import httpx

from .utils import HOST, get_available_port

_DEFAULT_DEV_SERVER_PORT = 8288


class _Server:
    _process: typing.Optional[subprocess.Popen[str]] = None
    _stop_printing: threading.Event
    _thread: typing.Optional[threading.Thread] = None

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    def __init__(self) -> None:
        self._enabled = os.getenv("DEV_SERVER_ENABLED") != "0"
        self.host = HOST

        port: int
        dev_server_port_env_var = os.getenv("DEV_SERVER_PORT")
        if dev_server_port_env_var:
            port = int(dev_server_port_env_var)
        elif self._enabled:
            port = get_available_port()
        else:
            port = _DEFAULT_DEV_SERVER_PORT
        self.port = port

        self._stop_printing = threading.Event()

    def _print_output(self, out_queue: queue.Queue[str]) -> None:
        while self._stop_printing.is_set() is False:
            try:
                line = out_queue.get(timeout=0.1)
                sys.stdout.write(line)
                sys.stdout.flush()
            except queue.Empty:
                continue

    def start(self) -> None:
        if self._enabled is False:
            return
        print("Inngest Server: starting")

        out_queue = queue.Queue[str]()

        def _run() -> None:
            process = subprocess.Popen(
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
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                universal_newlines=True,
            )

            self._process = process

            if process.stderr:
                for line in iter(process.stderr.readline, ""):
                    # IMPORTANT: Don't break this loop. If you do then the
                    # buffer may fill and the process will hang

                    if self._stop_printing.is_set() is False:
                        out_queue.put(line)

            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    # IMPORTANT: Don't break this loop. If you do then the
                    # buffer may fill and the process will hang

                    if self._stop_printing.is_set() is False:
                        out_queue.put(line)

        self._thread = threading.Thread(target=_run)
        self._thread.start()

        self._print_thread = threading.Thread(
            target=self._print_output,
            args=(out_queue,),
        )
        self._print_thread.start()

        print("Inngest Server: waiting for start")
        start_time = time.time()
        while True:
            if time.time() - start_time > 30:
                raise Exception("timeout waiting for Inngest Server to start")

            try:
                httpx.get(f"http://127.0.0.1:{self.port}")
                break
            except Exception:
                pass

        # Stop printing stdout and stderr
        self._stop_printing.set()
        self._print_thread.join(timeout=1)

        print("Inngest Server: started")

    def stop(self) -> None:
        if not self._enabled:
            return
        print("Inngest Server: stopping")

        if self._process is None:
            raise Exception("missing process")

        self._process.send_signal(signal.SIGINT)

        # Try to gracefully stop but kill it if that fails.
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)


server = _Server()
