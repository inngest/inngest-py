from __future__ import annotations

import dataclasses
import http.server
import json
import socketserver
import threading
import typing

import fastapi.testclient
import flask.testing

from . import net


class Proxy:
    _port: int
    _thread: typing.Optional[threading.Thread] = None

    @property
    def host(self) -> str:
        return net.HOST

    @property
    def port(self) -> int:
        return self._port

    def __init__(self, on_request: OnRequest) -> None:
        self._port = net.get_available_port()

        class _Handler(http.server.SimpleHTTPRequestHandler):
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
                body = None
                content_length = self.headers.get("Content-Length")
                if content_length is not None:
                    body = self.rfile.read(int(content_length))

                res = on_request(
                    body=body,
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
                body = None
                content_length = self.headers.get("Content-Length")
                if content_length is not None:
                    body = self.rfile.read(int(content_length))

                res = on_request(
                    body=body,
                    headers=self._get_headers(),
                    method="PATCH",
                    path=self.path,
                )
                self._set_response(res)

            def do_POST(self) -> None:
                body = None
                content_length = self.headers.get("Content-Length")
                if content_length is not None:
                    body = self.rfile.read(int(content_length))

                res = on_request(
                    body=body,
                    headers=self._get_headers(),
                    method="POST",
                    path=self.path,
                )
                self._set_response(res)

            def do_PUT(self) -> None:
                body = None
                content_length = self.headers.get("Content-Length")
                if content_length is not None:
                    body = self.rfile.read(int(content_length))

                res = on_request(
                    body=body,
                    headers=self._get_headers(),
                    method="PUT",
                    path=self.path,
                )
                self._set_response(res)

            def log_message(self, *args: object, **kwargs: object) -> None:
                # Silence logs
                pass

        self._server = socketserver.TCPServer((self.host, self.port), _Handler)

    def start(self) -> Proxy:
        self._thread = threading.Thread(
            daemon=True,
            target=self._server.serve_forever,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()

        if self._thread is None:
            raise Exception("missing thread")
        self._thread.join(timeout=5)


@dataclasses.dataclass
class Response:
    body: typing.Optional[bytes]
    headers: dict[str, str]
    status_code: int


class OnRequest(typing.Protocol):
    def __call__(
        self,
        *,
        body: typing.Optional[bytes],
        headers: dict[str, list[str]],
        method: str,
        path: str,
    ) -> Response: ...


def on_proxy_fast_api_request(
    client: fastapi.testclient.TestClient,
    *,
    body: typing.Optional[bytes],
    headers: dict[str, list[str]],
    method: str,
    path: str,
) -> Response:
    if body is None or len(body) == 0:
        body = json.dumps({}).encode("utf-8")

    new_headers = {key: value[0] for key, value in headers.items()}

    if method == "POST":
        res = client.post(
            path,
            content=body,
            headers=new_headers,
        )
    elif method == "PUT":
        res = client.put(
            path,
            content=body,
            headers=new_headers,
        )
    else:
        raise Exception(f"unsupported method: {method}")

    return Response(
        body=res.content,
        headers=dict(res.headers),
        status_code=res.status_code,
    )


def on_proxy_flask_request(
    client: flask.testing.FlaskClient,
    *,
    body: typing.Optional[bytes],
    headers: dict[str, list[str]],
    method: str,
    path: str,
) -> Response:
    res = client.open(
        method=method,
        path=path,
        headers=headers,
        data=body,
    )

    return Response(
        body=res.data,
        headers=dict(res.headers),
        status_code=res.status_code,
    )
