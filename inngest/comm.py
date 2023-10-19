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
class Response:
    headers: dict[str, str]
    status_code: int
    body: str = ""


class InngestCommHandler:
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
    ) -> Response:
        if fn_id not in self._fns:
            raise Exception(f"function {fn_id} not found")

        body: str
        status_code: int
        headers: dict[str, str] = {}
        res = self._fns[fn_id].call(call)
        if isinstance(res, list):
            out: list[dict[str, object]] = []
            for item in res:
                if not isinstance(item, ActionResponse):
                    raise Exception("expected ActionResponse")

                out.append(item.to_dict())

            body = json.dumps(_remove_none_deep(out))
            status_code = 206
        elif isinstance(res, ActionError):
            body = json.dumps(_remove_none_deep(res.to_dict()))
            status_code = 500

            if res.is_retriable is False:
                headers["x-inngest-no-retry"] = "true"
        else:
            body = res
            status_code = 200

        return Response(
            body=body,
            headers=headers,
            status_code=status_code,
        )

    def _get_function_configs(self, app_url: str) -> list[FunctionConfig]:
        return [fn.get_config(app_url) for fn in self._fns.values()]

    def handle_action(self) -> None:
        return None

    def register(self, app_url: str) -> Response:
        parsed_url = urlparse(self._base_url)

        if parsed_url.scheme == "https":
            conn = http.client.HTTPSConnection(parsed_url.netloc)
        else:
            conn = http.client.HTTPConnection(parsed_url.netloc)

        headers = {
            "Content-Type": "application/json",
            "Server-Timing": "handler",
            "User-Agent": f"inngest-{LANGUAGE}:v{VERSION}",
            "x-inngest-framework": self._framework,
            "x-inngest-sdk": f"inngest-{LANGUAGE}:v{VERSION}",
        }

        if self._signing_key:
            headers["Authorization"] = f"Bearer {_hash_signing(self._signing_key)}"

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

        conn.request(
            "POST",
            parsed_url.path,
            body=req_body,
            headers=headers,
        )
        res = conn.getresponse()

        out = Response(
            headers={
                "Content-Type": "application/json",
            },
            status_code=0,
        )
        out_body: dict[str, object] = {}

        res_body: dict[str, object] | None = None
        try:
            raw_body = json.loads(res.read().decode("utf-8"))
            if isinstance(raw_body, dict):
                res_body = raw_body
        except Exception as err:
            self._logger.error(
                "registration response body is not JSON",
                extra={"err": str(err)},
            )

        if res_body is None:
            self._logger.error(
                "registration response body is not an object",
                extra={"body": res_body},
            )

        if res.status < 400:
            if res_body:
                message = res_body.get("message")
                if isinstance(message, str):
                    out_body["message"] = message

                modified = res_body.get("modified")
                if isinstance(modified, bool):
                    out_body["modified"] = modified

            out.status_code = 200
        else:
            extra: dict[str, object] = {"status": res.status}

            if res_body:
                error = res_body.get("error")
                if isinstance(error, str):
                    out_body["message"] = error
                    extra["error"] = res_body.get("error")

            self._logger.error(
                "registration response failed",
                extra=extra,
            )

            out.status_code = res.status

        out.body = json.dumps(out_body)

        conn.close()
        return out


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
