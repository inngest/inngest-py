from __future__ import annotations

import logging
import os
import urllib.parse

import requests

from . import (
    client_lib,
    const,
    errors,
    execution,
    function,
    function_config,
    net,
    registration,
    transforms,
)


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
            self.headers[
                const.HeaderKey.CONTENT_TYPE.value
            ] = "application/json"
        else:
            self.headers[const.HeaderKey.CONTENT_TYPE.value] = "text/plain"


class CommHandler:
    def __init__(
        self,
        *,
        api_origin: str | None = None,
        client: client_lib.Inngest,
        framework: str,
        functions: list[function.Function],
        logger: logging.Logger,
        signing_key: str | None = None,
    ) -> None:
        self._is_production = client.is_production
        self._logger = logger

        if not self._is_production:
            self._logger.info("Dev Server mode enabled")

        api_origin = api_origin or os.getenv(const.EnvKey.BASE_URL.value)

        if api_origin is None:
            if not self._is_production:
                self._logger.info("Defaulting API origin to Dev Server")
                api_origin = const.DEV_SERVER_ORIGIN
            else:
                api_origin = const.DEFAULT_API_ORIGIN

        try:
            self._base_url = net.parse_url(api_origin)
        except Exception as err:
            raise errors.InvalidBaseURL() from err

        self._client = client
        self._fns: dict[str, function.Function] = {
            fn.get_id(): fn for fn in functions
        }
        self._framework = framework
        self._signing_key = signing_key or os.getenv(
            const.EnvKey.SIGNING_KEY.value
        )

    def call_function(
        self,
        *,
        call: execution.Call,
        fn_id: str,
        req_sig: net.RequestSignature,
    ) -> CommResponse:
        """
        Handles a function call from the Executor.
        """

        try:
            req_sig.validate(self._signing_key)

            # Look for the function ID in the list of user functions, but also
            # look for it in the list of on_failure functions.
            fn: function.Function | None = None
            for _fn in self._fns.values():
                if _fn.get_id() == fn_id:
                    fn = _fn
                    break
                if _fn.on_failure_fn_id == fn_id:
                    fn = _fn
                    break

            if fn is None:
                raise errors.MissingFunction(f"function {fn_id} not found")

            comm_res = CommResponse(
                headers={
                    **net.create_headers(framework=self._framework),
                    const.HeaderKey.SERVER_TIMING.value: "handler",
                }
            )

            action_res = fn.call(call, self._client, fn_id)
            if isinstance(action_res, list):
                out: list[dict[str, object]] = []
                for item in action_res:
                    out.append(item.to_dict())

                comm_res.body = transforms.prep_body(out)
                comm_res.status_code = 206
            elif isinstance(action_res, execution.CallError):
                comm_res.body = transforms.prep_body(action_res.model_dump())
                comm_res.status_code = 500

                if action_res.is_retriable is False:
                    comm_res.headers[const.HeaderKey.NO_RETRY.value] = "true"
            else:
                comm_res.body = action_res

            return comm_res
        except errors.InternalError as err:
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
                headers=net.create_headers(framework=self._framework),
                status_code=err.status_code,
            )

    def get_function_configs(
        self, app_url: str
    ) -> list[function_config.FunctionConfig]:
        configs: list[function_config.FunctionConfig] = []
        for fn in self._fns.values():
            config = fn.get_config(app_url)
            configs.append(config.main)

            if config.on_failure is not None:
                configs.append(config.on_failure)

        if len(configs) == 0:
            raise errors.InvalidConfig("no functions found")
        return configs

    def _parse_registration_response(
        self,
        server_res: requests.Response,
    ) -> CommResponse:
        comm_res = CommResponse(
            headers=net.create_headers(framework=self._framework)
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
            if is_from_dev_server and self._is_production:
                self._logger.error(
                    "Dev Server registration not allowed in production mode"
                )

                return CommResponse(
                    body={
                        "code": const.ErrorCode.DEV_SERVER_REGISTRATION_NOT_ALLOWED.value,
                        "message": "dev server not allowed",
                    },
                    headers={},
                    status_code=400,
                )

            registration_url = urllib.parse.urljoin(
                self._base_url,
                "/fn/register",
            )

            body = transforms.prep_body(
                registration.RegisterRequest(
                    app_name=self._client.app_id,
                    deploy_type=registration.DeployType.PING,
                    framework=self._framework,
                    functions=self.get_function_configs(app_url),
                    sdk=f"{const.LANGUAGE}:v{const.VERSION}",
                    url=app_url,
                    # TODO: Do this for real.
                    v="0.1",
                ).to_dict()
            )

            headers = net.create_headers(framework=self._framework)
            if self._signing_key:
                headers[
                    "Authorization"
                ] = f"Bearer {transforms.hash_signing_key(self._signing_key)}"

            res = net.requests_session.post(
                registration_url,
                json=body,
                headers=headers,
                timeout=30,
            )

            return self._parse_registration_response(res)
        except errors.InternalError as err:
            self._logger.error(
                "registration failed",
                extra={
                    "error_code": err.code,
                    "error_message": str(err),
                },
            )

            return CommResponse(
                body={
                    "code": err.code,
                    "message": str(err),
                },
                headers=net.create_headers(framework=self._framework),
                status_code=err.status_code,
            )
