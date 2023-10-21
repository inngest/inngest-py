from __future__ import annotations

import socketserver
import threading
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler
from typing import Protocol

from .net import HOST, get_available_port


class HTTPProxy:
    _port: int
    _thread: threading.Thread | None = None

    def __init__(self, on_request: _OnRequest) -> None:
        self._port = get_available_port()

        class _Handler(SimpleHTTPRequestHandler):
            def _get_headers(self) -> dict[str, list[str]]:
                headers: dict[str, list[str]] = {}
                for key, value in self.headers.items():
                    if key in headers:
                        headers[key].append(value)
                        continue

                    headers[key] = [value]

                return headers

            def _set_response(self, res: Response) -> None:
                self.send_response(res.status_code)

                for key, value in res.headers.items():
                    self.send_header(key, value)
                self.end_headers()

                if res.body is not None:
                    self.wfile.write(res.body)

            def do_DELETE(self) -> None:
                res = on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="DELETE",
                    path=self.path,
                )
                self._set_response(res)

            def do_GET(self) -> None:
                res = on_request(
                    body=None,
                    headers=self._get_headers(),
                    method="GET",
                    path=self.path,
                )
                self._set_response(res)

            def do_PATCH(self) -> None:
                res = on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="PATCH",
                    path=self.path,
                )
                self._set_response(res)

            def do_POST(self) -> None:
                res = on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="POST",
                    path=self.path,
                )
                self._set_response(res)

            def do_PUT(self) -> None:
                res = on_request(
                    body=self.rfile.read(int(self.headers["Content-Length"])),
                    headers=self._get_headers(),
                    method="PUT",
                    path=self.path,
                )
                self._set_response(res)

        self._server = socketserver.TCPServer((self.host, self.port), _Handler)

    @property
    def host(self) -> str:
        return HOST

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> HTTPProxy:
        self._thread = threading.Thread(daemon=True, target=self._server.serve_forever)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()

        if self._thread is None:
            raise Exception("missing thread")
        self._thread.join(timeout=5)


@dataclass
class Response:
    body: bytes | None
    headers: dict[str, str]
    status_code: int


class _OnRequest(Protocol):
    def __call__(
        self,
        *,
        body: bytes | None,
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> Response:
        ...
