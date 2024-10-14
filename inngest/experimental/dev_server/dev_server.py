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


class _DevServer:
    _process: typing.Optional[subprocess.Popen[bytes]] = None
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

    def _print_output(self, out_queue: queue.Queue[bytes]) -> None:
        while not self._stop_printing.is_set():
            try:
                line = out_queue.get(timeout=0.1)
                sys.stdout.write(line.decode("utf-8"))
                sys.stdout.flush()
            except queue.Empty:
                continue

    def start(self) -> None:
        if not self._enabled:
            return
        print("Inngest Server: starting")

        out_queue = queue.Queue[bytes]()

        def _run() -> None:
            process = subprocess.Popen(
                [
                    "npx",
                    "--yes",
                    "inngest-cli@1.0.4",
                    "dev",
                    "--no-discovery",
                    "--no-poll",
                    "--port",
                    f"{self.port}",
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )

            self._process = process

            if process.stderr:
                for line in iter(process.stderr.readline, ""):
                    out_queue.put(line)
                    if self._stop_printing.is_set():
                        break

            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    out_queue.put(line)
                    if self._stop_printing.is_set():
                        break

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
        self._print_thread.join()

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


server = _DevServer()
