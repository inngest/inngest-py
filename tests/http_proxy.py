from __future__ import annotations
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading
import time
from typing import Protocol


class _OnRequest(Protocol):
    def __call__(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> object:
        ...


class HTTPProxy:
    _thread: threading.Thread | None = None

    def __init__(self, on_request: _OnRequest) -> None:
        class _Handler(SimpleHTTPRequestHandler):
            def _get_headers(self) -> dict[str, list[str]]:
                headers: dict[str, list[str]] = {}
                for key, value in self.headers.items():
                    if key in headers:
                        headers[key].append(value)
                        continue

                    headers[key] = [value]

                return headers

            def _set_response(self):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()

            def do_DELETE(self):
                on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="DELETE",
                    path=self.path,
                )
                self._set_response()

            def do_GET(self):
                on_request(
                    body=None,
                    headers=self._get_headers(),
                    method="GET",
                    path=self.path,
                )
                self._set_response()

            def do_PATCH(self):
                on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="PATCH",
                    path=self.path,
                )
                self._set_response()

            def do_POST(self):
                on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="POST",
                    path=self.path,
                )
                self._set_response()

            def do_PUT(self):
                on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="PUT",
                    path=self.path,
                )
                self._set_response()

        self._server = socketserver.TCPServer(("", 9000), _Handler)

    # def on_request(
    #     self,
    #     *,
    #     body: bytes | None,
    #     headers: dict[str, list[str]],
    #     method: str,
    #     path: str,
    # ) -> None:
    #     print(method)
    #     print(headers)
    #     print(body)

    def start(self) -> HTTPProxy:
        self._thread = threading.Thread(daemon=True, target=self._server.serve_forever)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()

        if self._thread is None:
            raise Exception("missing thread")
        self._thread.join(timeout=5)


# proxy = Proxy()
# proxy.start()
# # print(1)
# time.sleep(100)
# # proxy.stop()


# # server = HTTPServer(("localhost", 9000), _Handler)
# # try:
# #     server.serve_forever()
# # except KeyboardInterrupt:
# #     pass
# # server.server_close()
