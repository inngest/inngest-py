from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from logging import Logger
from urllib.parse import parse_qs, urljoin

import requests

from .client import Inngest
from .const import (
    DEFAULT_API_ORIGIN,
    DEV_SERVER_ORIGIN,
    LANGUAGE,
    VERSION,
    EnvKey,
    ErrorCode,
    HeaderKey,
)
from .env import is_prod
from .errors import (
    InvalidBaseURL,
    InvalidRequestSignature,
    MissingHeader,
    MissingSigningKey,
)
from .execution import Call, CallError, CallResponse
from .function import Function
from .function_config import FunctionConfig
from .net import create_headers, parse_url, requests_session
from .registration import DeployType, RegisterRequest
from .transforms import (
    hash_signing_key,
    remove_none_deep,
    remove_signing_key_prefix,
)


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

        if not is_prod():
            self._logger.info("Dev Server mode enabled")

        api_origin = api_origin or os.getenv(EnvKey.BASE_URL.value)

        if api_origin is None:
            if not is_prod():
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
        req_sig: RequestSignature,
    ) -> CommResponse:
        """
        Handles a function call from the Executor.
        """

        req_sig.validate(self._signing_key)

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

            comm_res.body = remove_none_deep(out)
            comm_res.status_code = 206
        elif isinstance(action_res, CallError):
            comm_res.body = remove_none_deep(action_res.model_dump())
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
        server_res: requests.Response,
    ) -> CommResponse:
        comm_res = CommResponse(
            headers=create_headers(framework=self._framework)
        )
        body: dict[str, object] = {}

        server_res_body: dict[str, object] | None = None
        try:
            raw_body: object = server_res.json()
            if isinstance(raw_body, dict):
                server_res_body = raw_body
        except Exception:
            pass

        if server_res.status_code < 400:
            if server_res_body:
                message = server_res_body.get("message")
                if isinstance(message, str):
                    body["message"] = message

                modified = server_res_body.get("modified")
                if isinstance(modified, bool):
                    body["modified"] = modified
        else:
            extra: dict[str, object] = {"status_code": server_res.status_code}

            if server_res_body:
                error = server_res_body.get("error")
                if isinstance(error, str):
                    body["message"] = error
                    extra["error"] = server_res_body.get("error")

            self._logger.error(
                "registration response failed",
                extra=extra,
            )

            comm_res.status_code = server_res.status_code

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

        if is_from_dev_server and is_prod():
            self._logger.error(
                "Dev Server registration not allowed in production mode"
            )

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

        body = remove_none_deep(
            RegisterRequest(
                app_name=self._client.id,
                deploy_type=DeployType.PING,
                framework=self._framework,
                functions=self._get_function_configs(app_url),
                sdk=f"{LANGUAGE}:v{VERSION}",
                url=app_url,
                # TODO: Do this for real.
                v="0.1",
            ).to_dict()
        )

        headers = create_headers(framework=self._framework)
        if self._signing_key:
            headers[
                "Authorization"
            ] = f"Bearer {hash_signing_key(self._signing_key)}"

        res = requests_session.post(
            registration_url,
            json=body,
            headers=headers,
            timeout=30,
        )

        return self._parse_registration_response(res)


class RequestSignature:
    _signature: str | None = None
    _timestamp: int | None = None

    def __init__(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        self._body = body

        sig_header = headers.get(HeaderKey.SIGNATURE.value)
        if sig_header is not None:
            parsed = parse_qs(sig_header)
            if "t" in parsed:
                self._timestamp = int(parsed["t"][0])
            if "s" in parsed:
                self._signature = parsed["s"][0]

    def validate(self, signing_key: str | None) -> None:
        if not is_prod():
            return

        if signing_key is None:
            raise MissingSigningKey(
                "cannot validate signature in production mode without a signing key"
            )

        if self._signature is None:
            raise MissingHeader(
                f"cannot validate signature in production mode without a {HeaderKey.SIGNATURE.value} header"
            )

        mac = hmac.new(
            remove_signing_key_prefix(signing_key).encode("utf-8"),
            self._body,
            hashlib.sha256,
        )
        mac.update(str(self._timestamp).encode())
        if not hmac.compare_digest(self._signature, mac.hexdigest()):
            raise InvalidRequestSignature()
