from __future__ import annotations
from dataclasses import dataclass
import hashlib
import http.client
import json
from logging import Logger
import os
import re
from urllib.parse import urljoin

from .client import Inngest
from .const import (
    DEFAULT_API_ORIGIN,
    DEV_SERVER_ORIGIN,
    EnvKey,
    ErrorCode,
    LANGUAGE,
    VERSION,
)
from .env import allow_dev_server
from .errors import InvalidBaseURL
from .execution import Call, CallError, CallResponse
from .net import create_headers, Fetch, parse_url
from .function import Function
from .function_config import FunctionConfig
from .registration import RegisterRequest
from .types import T


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
        api_origin: str | None = None,
        client: Inngest,
        framework: str,
        functions: list[Function],
        logger: Logger,
        signing_key: str | None = None,
    ) -> None:
        self._logger = logger

        if allow_dev_server():
            self._logger.info("Dev Server mode enabled")

        api_origin = api_origin or os.getenv(EnvKey.BASE_URL.value)

        if api_origin is None:
            if allow_dev_server():
                self._logger.info("Defaulting API origin to Dev Server")
                api_origin = DEV_SERVER_ORIGIN
            else:
                api_origin = DEFAULT_API_ORIGIN

        try:
            self._base_url = parse_url(api_origin)
        except Exception as err:
            raise InvalidBaseURL("invalid base_url") from err

        self._client = client
        self._fns: dict[str, Function] = {fn.get_id(): fn for fn in functions}
        self._framework = framework
        self._signing_key = signing_key or os.getenv(EnvKey.SIGNING_KEY.value)

    def call_function(
        self,
        *,
        call: Call,
        fn_id: str,
    ) -> CommResponse:
        """
        Handles a function call from the Executor.
        """

        if fn_id not in self._fns:
            raise Exception(f"function {fn_id} not found")

        comm_res = CommResponse(
            headers={
                **create_headers(framework=self._framework),
                "Server-Timing": "handler",
            }
        )

        action_res = self._fns[fn_id].call(call, self._client)
        if isinstance(action_res, list):
            out: list[dict[str, object]] = []
            for item in action_res:
                if not isinstance(item, CallResponse):
                    raise Exception("expected CallResponse")

                out.append(item.to_dict())

            comm_res.body = _remove_none_deep(out)
            comm_res.status_code = 206
        elif isinstance(action_res, CallError):
            comm_res.body = _remove_none_deep(action_res.model_dump())
            comm_res.status_code = 500

            if action_res.is_retriable is False:
                comm_res.headers["x-inngest-no-retry"] = "true"
        else:
            comm_res.body = action_res

        return comm_res

    def _get_function_configs(self, app_url: str) -> list[FunctionConfig]:
        return [fn.get_config(app_url) for fn in self._fns.values()]

    def _parse_registration_response(
        self,
        server_res: http.client.HTTPResponse,
    ) -> CommResponse:
        comm_res = CommResponse(headers=create_headers(framework=self._framework))
        body: dict[str, object] = {}

        server_res_body: dict[str, object] | None = None
        try:
            raw_body = json.loads(server_res.read().decode("utf-8"))
            if isinstance(raw_body, dict):
                server_res_body = raw_body
        except Exception:
            pass

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

    def register(
        self,
        *,
        app_url: str,
        is_from_dev_server: bool,
    ) -> CommResponse:
        """
        Handles a registration call.
        """

        if is_from_dev_server and not allow_dev_server():
            self._logger.error("Dev Server registration not allowed in production mode")

            comm_res = CommResponse(
                headers={},
                status_code=400,
            )
            comm_res.body = {
                "code": ErrorCode.DEV_SERVER_REGISTRATION_NOT_ALLOWED.value,
                "message": "dev server not allowed",
            }
            return comm_res

        registration_url = urljoin(self._base_url, "/fn/register")

        body = _remove_none_deep(
            RegisterRequest(
                app_name=self._client.id,
                framework=self._framework,
                functions=self._get_function_configs(app_url),
                # TODO: Do this for real.
                hash="094cd50f64aadfec073d184bedd7b7d077f919b3d5a19248bb9a68edbc66597c",
                sdk=f"{LANGUAGE}:v{VERSION}",
                url=app_url,
                # TODO: Do this for real.
                v="0.1",
            ).to_dict()
        )

        headers = create_headers(framework=self._framework)
        if self._signing_key:
            headers["Authorization"] = f"Bearer {_hash_signing(self._signing_key)}"

        with Fetch.post(registration_url, body, headers) as res:
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


def _remove_none_deep(obj: T) -> T:
    if isinstance(obj, dict):
        return {k: _remove_none_deep(v) for k, v in obj.items() if v is not None}  # type: ignore
    if isinstance(obj, list):
        return [_remove_none_deep(v) for v in obj if v is not None]  # type: ignore
    return obj
