"""
An in-memory sandbox REST API for tests, served through httpx.MockTransport.

State changes take effect on the next GET, so the SDK's polling runs at least
once. Shared by the direct-client and durable tests.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import re
import typing
import uuid

import httpx

import inngest
from inngest._internal import net, transforms
from inngest._internal.sandbox_lib import ops

NOW: typing.Final = "2026-10-14T12:00:00Z"
LATER: typing.Final = "2026-10-15T12:00:00Z"
SIGNING_KEY: typing.Final = "signkey-test-12345678"
FALLBACK_KEY: typing.Final = "signkey-test-abcdef01"

_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@dataclasses.dataclass
class Call:
    key: str
    request: httpx.Request

    @property
    def json(self) -> typing.Any:
        if self.request.content == b"":
            return None
        return json.loads(self.request.content)

    @property
    def query(self) -> dict[str, str]:
        return dict(self.request.url.params)

    @property
    def auth(self) -> str | None:
        return typing.cast(
            "str | None", self.request.headers.get("authorization")
        )


class FakeAPI:
    def __init__(self) -> None:
        self.sandboxes: dict[str, dict[str, typing.Any]] = {}
        self.next_status: dict[str, str] = {}
        self.snapshots: dict[str, dict[str, typing.Any]] = {}
        self.processes: dict[str, dict[str, typing.Any]] = {}
        self.files: dict[str, bytes] = {}
        self.calls: list[Call] = []

        # One-shot failures by route key, like "POST /v2/sandboxes".
        self.fail: dict[str, tuple[int, str]] = {}
        self.raise_transport_error: dict[str, type[httpx.TransportError]] = {}

        # Requests with this Authorization header get reject_auth_status.
        self.reject_auth: str | None = None
        self.reject_auth_status = 401

        self.exec_stdout: bytes | None = None
        self.exec_stderr = b"warn"
        self.exec_exit_code = 3
        self.stream_lines: list[str] | None = None
        self.download_content_length: int | None = None

        self.transport = httpx.MockTransport(self._handle)

    def client(
        self,
        *,
        signing_key: str | None = SIGNING_KEY,
        is_production: bool = True,
    ) -> inngest.Inngest:
        client = inngest.Inngest(
            app_id="sandbox-test",
            api_base_url="http://sandbox.test",
            is_production=is_production,
            signing_key=signing_key,
        )
        client._http_client._http_client_sync = httpx.Client(
            transport=self.transport
        )
        client._http_client._http_client = net.ThreadAwareAsyncHTTPClient(
            transport=self.transport
        ).initialize()
        return client

    def count(self, key: str) -> int:
        return sum(1 for c in self.calls if c.key == key)

    def keys(self) -> list[str]:
        return [c.key for c in self.calls]

    def last(self, key: str) -> Call:
        return [c for c in self.calls if c.key == key][-1]

    def add_sandbox(self, status: str = "RUNNING") -> dict[str, typing.Any]:
        info = _sandbox_info("existing", status, {"vcpu": 1, "memoryMb": 1024})
        self.sandboxes[info["id"]] = info
        return info

    # --- Routing ------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.strip("/").split("/")
        key = (
            request.method
            + " /"
            + "/".join("{id}" if _UUID.match(p) else p for p in parts)
        )
        self.calls.append(Call(key, request))

        transport_error = self.raise_transport_error.pop(key, None)
        if transport_error is not None:
            raise transport_error("connection failed", request=request)
        if (
            self.reject_auth is not None
            and request.headers.get("authorization") == self.reject_auth
        ):
            return _error(self.reject_auth_status, "unauthorized")
        failure = self.fail.pop(key, None)
        if failure is not None:
            return _error(*failure)

        if key == "POST /v2/sandboxes":
            return self._create(json.loads(request.content))
        if key == "GET /v2/sandboxes":
            return _list(list(self.sandboxes.values()))
        if key == "GET /v2/snapshots":
            name = request.url.params.get("name")
            return _list(
                [
                    s
                    for s in self.snapshots.values()
                    if name is None or s.get("name") == name
                ]
            )
        if key == "GET /v2/snapshots/{id}":
            snapshot = self.snapshots.get(parts[2])
            if snapshot is None:
                return _error(404, "sandbox_snapshot_not_found")
            snapshot.update(status="READY", compatibilityId="compat-1")
            return _data(200, snapshot)
        if key == "DELETE /v2/snapshots/{id}":
            if self.snapshots.pop(parts[2], None) is None:
                return _error(404, "sandbox_snapshot_not_found")
            return httpx.Response(204)
        if parts[:2] == ["v2", "sandboxes"] and len(parts) >= 3:
            sandbox = self.sandboxes.get(parts[2])
            if sandbox is None:
                return _error(404, "sandbox_not_found")
            return self._sandbox(key, request, sandbox, parts)
        raise AssertionError(f"unexpected request {key}")

    def _create(self, body: dict[str, typing.Any]) -> httpx.Response:
        resources = {"vcpu": body.get("vcpu"), "memoryMb": body.get("memoryMb")}
        if "snapshotId" in body:
            snapshot = self.snapshots.get(body["snapshotId"])
            if snapshot is None:
                return _error(404, "sandbox_snapshot_not_found")
            resources = snapshot["resources"]
        for existing in self.sandboxes.values():
            if existing["name"] == body["name"]:
                if existing["resources"] != resources:
                    return _error(409, "sandbox_name_taken")
                return _data(200, existing)
        info = _sandbox_info(body["name"], "STARTING", resources)
        if "image" in body:
            if body["image"] == "missing":
                return _error(404, "sandbox_image_not_found")
            info["imageRef"] = body["image"]
            info["imageDigest"] = "sha256:" + "d" * 64
        self.sandboxes[info["id"]] = info
        self.next_status[info["id"]] = "RUNNING"
        return _data(202, info)

    def _sandbox(
        self,
        key: str,
        request: httpx.Request,
        sandbox: dict[str, typing.Any],
        parts: list[str],
    ) -> httpx.Response:
        sandbox_id = sandbox["id"]
        if key == "GET /v2/sandboxes/{id}":
            if sandbox_id in self.next_status:
                sandbox["status"] = self.next_status.pop(sandbox_id)
            return _data(200, sandbox)
        if key == "DELETE /v2/sandboxes/{id}":
            del self.sandboxes[sandbox_id]
            return _data(202, {**sandbox, "status": "TERMINATING"})
        if key in (
            "POST /v2/sandboxes/{id}/pause",
            "POST /v2/sandboxes/{id}/resume",
        ):
            pausing = key.endswith("pause")
            sandbox["status"] = "PAUSING" if pausing else "RESUMING"
            self.next_status[sandbox_id] = "PAUSED" if pausing else "RUNNING"
            return _data(202, sandbox)
        if key == "POST /v2/sandboxes/{id}/exec":
            body = json.loads(request.content)
            stdout = self.exec_stdout
            if stdout is None:
                stdout = (
                    " ".join(body["command"]) + "|" + body["timeout"]
                ).encode()
            data: dict[str, typing.Any] = {
                "stdout": base64.b64encode(stdout).decode(),
                "stderr": base64.b64encode(self.exec_stderr).decode(),
                "encoding": "base64",
                "exitCode": self.exec_exit_code,
            }
            # The API omits empty output and a zero exit code.
            data = {k: v for k, v in data.items() if v not in ("", 0)}
            return _data(200, data)
        if key == "POST /v2/sandboxes/{id}/processes":
            body = json.loads(request.content)
            process = {
                "id": str(uuid.uuid4()),
                "command": body["command"],
                "pid": 42,
                "state": "RUNNING",
            }
            self.processes[process["id"]] = process
            return _data(201, process)
        if key == "GET /v2/sandboxes/{id}/processes":
            return _list(list(self.processes.values()))
        if key == "GET /v2/sandboxes/{id}/processes/{id}":
            found = self.processes.get(parts[4])
            if found is None:
                return _error(404, "sandbox_process_not_found")
            return _data(200, found)
        if key == "POST /v2/sandboxes/{id}/processes/{id}/signals":
            body = json.loads(request.content)
            self.processes[parts[4]].update(
                state="KILLED", terminationSignal=body["signal"]
            )
            return httpx.Response(204)
        if key == "POST /v2/sandboxes/{id}/processes/{id}/wait":
            return _data(
                200, {"id": parts[4], "state": "EXITED", "exitCode": 0}
            )
        if key == "GET /v2/sandboxes/{id}/processes/{id}/output":
            return _data(
                200,
                {
                    "chunks": [
                        {
                            "stream": "STDOUT",
                            "data": base64.b64encode(b"hello").decode(),
                            "encoding": "base64",
                            "at": NOW,
                        }
                    ]
                },
            )
        if key in (
            "GET /v2/sandboxes/{id}/processes/{id}/output/stream",
            "GET /v2/sandboxes/{id}/logs",
        ):
            lines = self.stream_lines
            if lines is None:
                lines = [
                    json.dumps(
                        {
                            "type": "log",
                            "stream": "STDOUT",
                            "data": base64.b64encode(s).decode(),
                            "encoding": "base64",
                        }
                    )
                    for s in (b"one", b"two")
                ]
            return httpx.Response(
                200,
                content="\n\n".join(lines).encode() + b"\n",
                headers={"content-type": "application/x-ndjson"},
            )
        if key == "PUT /v2/sandboxes/{id}/files":
            content = request.read()
            path = request.url.params["path"]
            self.files[path] = content
            return _data(200, {"path": path, "bytesWritten": len(content)})
        if key == "GET /v2/sandboxes/{id}/files":
            stored = self.files.get(request.url.params["path"])
            if stored is None:
                return _error(404, "sandbox_file_not_found")
            headers = {}
            if self.download_content_length is not None:
                headers["content-length"] = str(self.download_content_length)
            return httpx.Response(200, content=stored, headers=headers)
        if key == "POST /v2/sandboxes/{id}/snapshots":
            body = json.loads(request.content) if request.content else {}
            snapshot: dict[str, typing.Any] = {
                "id": str(uuid.uuid4()),
                "sourceImageId": "a" * 64,
                "status": "CREATING",
                "resources": sandbox["resources"],
                # The API sends 64-bit integers as strings.
                "storedBytes": "1024",
                "createdAt": NOW,
                "updatedAt": NOW,
                "expiresAt": LATER,
            }
            if "name" in body:
                snapshot["name"] = body["name"]
            self.snapshots[snapshot["id"]] = snapshot
            return _data(202, snapshot)
        raise AssertionError(f"unexpected request {key}")


def hashed(key: str) -> str:
    return f"Bearer {transforms.hash_signing_key(key)}"


def run_ops(fake: FakeAPI, op: ops.Op[typing.Any]) -> typing.Any:
    return fake.client().sandboxes_sync._transport.run(op)


def _sandbox_info(
    name: str, status: str, resources: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "status": status,
        "vpcId": str(uuid.uuid4()),
        "imageRef": "default",
        "resources": resources,
        "createdAt": NOW,
    }


def _data(status: int, data: object) -> httpx.Response:
    return httpx.Response(
        status,
        json={"data": data, "metadata": {"fetchedAt": NOW}},
        headers={"x-request-id": "req-1"},
    )


def _list(items: list[typing.Any]) -> httpx.Response:
    # Like the API, omit zero values: an empty data list and hasMore=false.
    body: dict[str, object] = {
        "page": {"limit": 50},
        "metadata": {"fetchedAt": NOW},
    }
    if len(items) > 0:
        body["data"] = items
    return httpx.Response(200, json=body)


def _error(status: int, code: str) -> httpx.Response:
    return httpx.Response(
        status,
        json={"errors": [{"code": code, "message": f"fake {code}"}]},
        headers={"x-request-id": "req-1"},
    )
