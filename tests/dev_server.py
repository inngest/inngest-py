import threading
import subprocess


class _DevServer:
    _process: subprocess.Popen | None = None
    _thread: threading.Thread | None = None

    def start(self) -> None:
        def _run() -> None:
            self._process = subprocess.Popen(
                [
                    "npx",
                    "inngest-cli@latest",
                    "dev",
                    "--no-discovery",
                    "--no-poll",
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
