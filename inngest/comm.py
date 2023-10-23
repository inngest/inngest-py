from __future__ import annotations

import os
from logging import Logger
from urllib.parse import urljoin

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
from .errors import InternalError, InvalidBaseURL, MissingFunction
from .execution import Call, CallError
from .function import Function
from .function_config import FunctionConfig
from .net import RequestSignature, create_headers, parse_url, requests_session
from .registration import DeployType, RegisterRequest
from .transforms import hash_signing_key, remove_none_deep


class CommResponse:
    _body: object | None = None

    def __init__(
        self,
        *,
        body: object | None = None,
        headers: dict[str, str],
        status_code: int = 200,
    ) -> None:
        self.headers = headers
        self.body = body
        self.status_code = status_code

    @property
    def body(self) -> object:
        return self._body or {}

    @body.setter
    def body(self, body: object) -> None:
        self._body = body

        if isinstance(body, (dict, list)):
            self.headers[HeaderKey.CONTENT_TYPE.value] = "application/json"
        else:
            self.headers[HeaderKey.CONTENT_TYPE.value] = "text/plain"


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
            raise InvalidBaseURL() from err

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

        try:
            req_sig.validate(self._signing_key)

            if fn_id not in self._fns:
                raise MissingFunction(f"function {fn_id} not found")

            comm_res = CommResponse(
                headers={
                    **create_headers(framework=self._framework),
                    HeaderKey.SERVER_TIMING.value: "handler",
                }
            )

            action_res = self._fns[fn_id].call(call, self._client)
            if isinstance(action_res, list):
                out: list[dict[str, object]] = []
                for item in action_res:
                    out.append(item.to_dict())

                comm_res.body = remove_none_deep(out)
                comm_res.status_code = 206
            elif isinstance(action_res, CallError):
                comm_res.body = remove_none_deep(action_res.model_dump())
                comm_res.status_code = 500

                if action_res.is_retriable is False:
                    comm_res.headers[HeaderKey.NO_RETRY.value] = "true"
            else:
                comm_res.body = action_res

            return comm_res
        except InternalError as err:
            body = {
                "code": str(err),
                "message": str(err),
            }
            self._logger.error(
                "function call failed",
                extra=body,
            )
            return CommResponse(
                body=body,
                headers=create_headers(framework=self._framework),
                status_code=err.status_code,
            )

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

        try:
            if is_from_dev_server and is_prod():
                self._logger.error(
                    "Dev Server registration not allowed in production mode"
                )

                return CommResponse(
                    body={
                        "code": ErrorCode.DEV_SERVER_REGISTRATION_NOT_ALLOWED.value,
                        "message": "dev server not allowed",
                    },
                    headers={},
                    status_code=400,
                )

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
        except InternalError as err:
            self._logger.error(
                "registration failed",
                extra={
                    "error_code": err.code.value,
                    "error_message": str(err),
                },
            )

            return CommResponse(
                body={
                    "code": err.code.value,
                    "message": str(err),
                },
                headers=create_headers(framework=self._framework),
                status_code=err.status_code,
            )
