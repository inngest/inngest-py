# ruff: noqa: S602, T201

import os
import pathlib
import queue
import signal
import subprocess
import threading
import time
import typing


class _CommandRunner:
    def __init__(
        self,
        command: str,
        *,
        log_path: pathlib.Path | None = None,
    ):
        self._command = command
        self._log_path = log_path
        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[str] = queue.Queue()
        self._stderr_queue: queue.Queue[str] = queue.Queue()
        self._stop_printing_flag = False
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._running = False

    def run(self) -> None:
        """
        Runs the command in a subprocess and starts threads for stdout and stderr (non-blocking).
        """

        if self._running:  # Prevent starting the command multiple times
            return

        self._running = True
        try:
            self._process = subprocess.Popen(
                self._command,
                preexec_fn=os.setsid,
                shell=True,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            )

            self._stdout_thread = threading.Thread(
                args=(self._process.stdout, self._stdout_queue),
                target=self._enqueue_output,
            )
            self._stderr_thread = threading.Thread(
                args=(self._process.stderr, self._stderr_queue),
                target=self._enqueue_output,
            )

            self._stdout_thread.daemon = True
            self._stderr_thread.daemon = True

            self._stdout_thread.start()
            self._stderr_thread.start()

            # Start printing in a separate thread so that run is non-blocking.
            printing_thread = threading.Thread(target=self._print_output)
            printing_thread.daemon = True
            printing_thread.start()

        except FileNotFoundError:
            print(f"command not found: {self._command}")
            self._running = False
        except Exception as e:
            print(f"an error occurred: {e}")
            self._running = False

    def _enqueue_output(
        self,
        stream: typing.IO[str],
        q: queue.Queue[str],
    ) -> None:
        try:
            if self._log_path:
                with open(self._log_path, "a") as f:
                    for line in iter(stream.readline, ""):
                        q.put(line.strip())
                        f.write(line)
                        f.flush()
            else:
                for line in iter(stream.readline, ""):
                    q.put(line.strip())
        except ValueError:
            pass

    def is_running(self) -> bool:
        return self._running

    def _print_output(self) -> None:
        while self._process is not None and (
            self._process.poll() is None
            or not self._stdout_queue.empty()
            or not self._stderr_queue.empty()
        ):
            self._print_queue(self._stdout_queue)
            self._print_queue(self._stderr_queue)
            time.sleep(0.01)

        # Print any remaining output after the process finishes.
        self._print_queue(self._stdout_queue)
        self._print_queue(self._stderr_queue)
        self._running = False

    def _print_queue(self, q: queue.Queue[str]) -> None:
        while not q.empty():
            line = q.get()
            if not self._stop_printing_flag:
                print(line)

    def stop_printing(self) -> None:
        self._stop_printing_flag = True

    def wait(self) -> None:
        if self._process:
            self._process.wait()

    def kill(self) -> None:
        if self._process:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except Exception as e:
                print(f"error killing process: {e}")
            finally:
                self._running = False
