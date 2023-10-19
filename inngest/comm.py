from __future__ import annotations
from dataclasses import dataclass
import hashlib
import http.client
import json
from logging import Logger
import os
import re
from typing import TypeVar
from urllib.parse import urlparse

from .client import Inngest
from .const import DEFAULT_INNGEST_BASE_URL, EnvKey, LANGUAGE, VERSION
from .errors import InvalidBaseURL
from .function import Function
from .types import (
    ActionError,
    ActionResponse,
    FunctionCall,
    FunctionConfig,
    RegisterRequest,
)


T = TypeVar("T")


@dataclass
class CommResponse:
    headers: dict[str, str]
    _body: object | None = None
    status_code: int = 200

    @property
    def body(self) -> object:
        return self._body or {}

    @body.setter
    def body(self, body: object) -> None:
        self._body = body

        if isinstance(body, (dict, list)):
            self.headers["Content-Type"] = "application/json"
        else:
            self.headers["Content-Type"] = "text/plain"


class CommHandler:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: Inngest,
        framework: str,
        functions: list[Function],
        logger: Logger,
        signing_key: str | None = None,
    ) -> None:
        try:
            self._base_url = _parse_url(
                base_url or os.getenv(EnvKey.BASE_URL.value) or DEFAULT_INNGEST_BASE_URL
            )
        except Exception as err:
            raise InvalidBaseURL("invalid base_url") from err

        self._client = client
        self._fns: dict[str, Function] = {fn.get_id(): fn for fn in functions}
        self._framework = framework
        self._logger = logger
        self._signing_key = signing_key or os.getenv(EnvKey.SIGNING_KEY.value)

    def call_function(
        self,
        *,
        call: FunctionCall,
        fn_id: str,
    ) -> CommResponse:
        if fn_id not in self._fns:
            raise Exception(f"function {fn_id} not found")

        comm_res = self._create_response()
        comm_res.headers["Server-Timing"] = "handler"

        action_res = self._fns[fn_id].call(call)
        if isinstance(action_res, list):
            out: list[dict[str, object]] = []
            for item in action_res:
                if not isinstance(item, ActionResponse):
                    raise Exception("expected ActionResponse")

                out.append(item.to_dict())

            comm_res.body = _remove_none_deep(out)
            comm_res.status_code = 206
        elif isinstance(action_res, ActionError):
            comm_res.body = _remove_none_deep(action_res.to_dict())
            comm_res.status_code = 500

            if action_res.is_retriable is False:
                comm_res.headers["x-inngest-no-retry"] = "true"
        else:
            comm_res.body = action_res

        return comm_res

    def _create_response(self) -> CommResponse:
        return CommResponse(
            headers={
                "Content-Type": "application/json",
                "Server-Timing": "handler",
                "User-Agent": f"inngest-{LANGUAGE}:v{VERSION}",
                "x-inngest-framework": self._framework,
                "x-inngest-sdk": f"inngest-{LANGUAGE}:v{VERSION}",
            }
        )

    def _get_function_configs(self, app_url: str) -> list[FunctionConfig]:
        return [fn.get_config(app_url) for fn in self._fns.values()]

    def _parse_registration_response(
        self,
        server_res: http.client.HTTPResponse,
    ) -> CommResponse:
        comm_res = self._create_response()
        body: dict[str, object] = {}

        server_res_body: dict[str, object] | None = None
        try:
            raw_body = json.loads(server_res.read().decode("utf-8"))
            if isinstance(raw_body, dict):
                server_res_body = raw_body
        except Exception as err:
            self._logger.error(
                "registration response body is not JSON",
                extra={"err": str(err)},
            )

        if server_res_body is None:
            self._logger.error(
                "registration response body is not an object",
                extra={"body": server_res_body},
            )

        if server_res.status < 400:
            if server_res_body:
                message = server_res_body.get("message")
                if isinstance(message, str):
                    body["message"] = message

                modified = server_res_body.get("modified")
                if isinstance(modified, bool):
                    body["modified"] = modified
        else:
            extra: dict[str, object] = {"status": server_res.status}

            if server_res_body:
                error = server_res_body.get("error")
                if isinstance(error, str):
                    body["message"] = error
                    extra["error"] = server_res_body.get("error")

            self._logger.error(
                "registration response failed",
                extra=extra,
            )

            comm_res.status_code = server_res.status

        comm_res.body = body
        return comm_res

    def register(self, app_url: str) -> CommResponse:
        parsed_url = urlparse(self._base_url)

        if parsed_url.scheme == "https":
            conn = http.client.HTTPSConnection(parsed_url.netloc)
        else:
            conn = http.client.HTTPConnection(parsed_url.netloc)

        req_body = json.dumps(
            _remove_none_deep(
                RegisterRequest(
                    app_name=self._client.id,
                    framework=self._framework,
                    functions=self._get_function_configs(app_url),
                    hash="094cd50f64aadfec073d184bedd7b7d077f919b3d5a19248bb9a68edbc66597c",
                    sdk=f"{LANGUAGE}:v{VERSION}",
                    url=app_url,
                    v="0.1",
                ).to_dict()
            )
        )

        headers = self._create_response().headers
        if self._signing_key:
            headers["Authorization"] = f"Bearer {_hash_signing(self._signing_key)}"

        conn.request(
            "POST",
            parsed_url.path,
            body=req_body,
            headers=headers,
        )
        res = conn.getresponse()
        conn.close()

        return self._parse_registration_response(res)


def _hash_signing(key: str) -> str:
    prefix_match = re.match(r"^signkey-[\w]+-", key)
    prefix = ""
    if prefix_match:
        prefix = prefix_match.group(0)

    key_without_prefix = key[len(prefix) :]
    hasher = hashlib.sha256()
    hasher.update(bytearray.fromhex(key_without_prefix))
    return hasher.hexdigest()


def _parse_url(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme == "":
        parsed._replace(scheme="https")

    return parsed.geturl()


def _remove_none_deep(obj: T) -> T:
    if isinstance(obj, dict):
        return {k: _remove_none_deep(v) for k, v in obj.items() if v is not None}  # type: ignore
    elif isinstance(obj, list):
        return [_remove_none_deep(v) for v in obj if v is not None]  # type: ignore
    else:
        return obj
