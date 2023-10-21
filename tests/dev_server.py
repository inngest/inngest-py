import subprocess
import threading

from .net import get_available_port


class _DevServer:
    _port: int | None = None
    _process: subprocess.Popen | None = None
    _thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise Exception("not running")
        return self._port

    def start(self) -> None:
        self._port = get_available_port()

        def _run() -> None:
            self._process = subprocess.Popen(
                [
                    "npx",
                    "inngest-cli@latest",
                    "dev",
                    "--no-discovery",
                    "--no-poll",
                    "--port",
                    f"{self._port}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._process.communicate()

        self._thread = threading.Thread(target=_run)
        self._thread.start()
        self._thread.join(timeout=10)

    def stop(self) -> None:
        if self._process is None:
            raise Exception("missing process")
        if self._thread is None:
            raise Exception("missing thread")

        if not self._thread.is_alive():
            raise Exception("thread is not alive")

        self._process.terminate()
        self._thread.join()


dev_server = _DevServer()
