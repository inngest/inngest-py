from __future__ import annotations

import logging
import os
import urllib.parse

import httpx

from inngest._internal import (
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

    @classmethod
    def from_internal_error(
        cls,
        err: errors.InternalError,
        framework: str,
    ) -> CommResponse:
        return cls(
            body={
                "code": err.code,
                "message": str(err),
            },
            headers=net.create_headers(framework=framework),
            status_code=err.status_code,
        )


class CommHandler:
    _base_url: str
    _client: client_lib.Inngest
    _fns: dict[str, function.Function | function.FunctionSync]
    _framework: str
    _is_production: bool
    _logger: logging.Logger
    _signing_key: str | None

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: client_lib.Inngest,
        framework: str,
        functions: list[function.Function] | list[function.FunctionSync],
        logger: logging.Logger,
        signing_key: str | None = None,
    ) -> None:
        self._is_production = client.is_production
        self._logger = logger

        if not self._is_production:
            self._logger.info("Dev Server mode enabled")

        base_url = base_url or os.getenv(const.EnvKey.BASE_URL.value)
        if base_url is None:
            if not self._is_production:
                self._logger.info("Defaulting API origin to Dev Server")
                base_url = const.DEV_SERVER_ORIGIN
            else:
                base_url = const.DEFAULT_API_ORIGIN

        try:
            self._api_origin = net.parse_url(base_url)
        except Exception as err:
            raise errors.InvalidBaseURL() from err

        self._client = client
        self._fns = {fn.get_id(): fn for fn in functions}
        self._framework = framework

        if signing_key is None:
            if self._client.is_production:
                signing_key = os.getenv(const.EnvKey.SIGNING_KEY.value)
                if signing_key is None:
                    self._logger.error("missing signing key")
                    raise errors.MissingSigningKey()
        self._signing_key = signing_key

    def _build_registration_request(
        self,
        app_url: str,
    ) -> httpx.Request:
        registration_url = urllib.parse.urljoin(
            self._api_origin,
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
                v="0.1",
            ).to_dict()
        )

        headers = net.create_headers(framework=self._framework)
        if self._signing_key:
            headers[
                "Authorization"
            ] = f"Bearer {transforms.hash_signing_key(self._signing_key)}"

        return httpx.Client().build_request(
            "POST",
            registration_url,
            headers=headers,
            json=body,
            timeout=30,
        )

    async def call_function(
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
            fn = self._get_function(fn_id)
            if not isinstance(fn, function.Function):
                raise errors.MismatchedSync(
                    f"function {fn_id} is not asynchronous"
                )

            return self._create_response(
                await fn.call(call, self._client, fn_id)
            )
        except errors.InternalError as err:
            return CommResponse.from_internal_error(err, self._framework)

    def call_function_sync(
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
            fn = self._get_function(fn_id)
            if not isinstance(fn, function.FunctionSync):
                raise errors.MismatchedSync(
                    f"function {fn_id} is not synchronous"
                )

            return self._create_response(fn.call(call, self._client, fn_id))
        except errors.InternalError as err:
            return CommResponse.from_internal_error(err, self._framework)

    def _create_response(
        self,
        call_res: list[execution.CallResponse] | str | execution.CallError,
    ) -> CommResponse:
        comm_res = CommResponse(
            headers={
                **net.create_headers(framework=self._framework),
                const.HeaderKey.SERVER_TIMING.value: "handler",
            }
        )

        if isinstance(call_res, list):
            out: list[dict[str, object]] = []
            for item in call_res:
                out.append(item.to_dict())

            comm_res.body = transforms.prep_body(out)
            comm_res.status_code = 206
        elif isinstance(call_res, execution.CallError):
            comm_res.body = transforms.prep_body(call_res.model_dump())
            comm_res.status_code = 500

            if call_res.is_retriable is False:
                comm_res.headers[const.HeaderKey.NO_RETRY.value] = "true"
        else:
            comm_res.body = call_res

        return comm_res

    def _get_function(
        self, fn_id: str
    ) -> function.Function | function.FunctionSync:
        # Look for the function ID in the list of user functions, but also
        # look for it in the list of on_failure functions.
        for _fn in self._fns.values():
            if _fn.get_id() == fn_id:
                return _fn
            if _fn.on_failure_fn_id == fn_id:
                return _fn

        raise errors.MissingFunction(f"function {fn_id} not found")

    def get_function_configs(
        self,
        app_url: str,
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
        server_res: httpx.Response,
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

    async def register(
        self,
        *,
        app_url: str,
        is_from_dev_server: bool,
    ) -> CommResponse:
        """
        Handles a registration call.
        """

        try:
            self._validate_registration(is_from_dev_server)

            async with httpx.AsyncClient() as client:
                res = await client.send(
                    self._build_registration_request(app_url),
                )

            return self._parse_registration_response(res)
        except errors.InternalError as err:
            return CommResponse.from_internal_error(err, self._framework)

    def register_sync(
        self,
        *,
        app_url: str,
        is_from_dev_server: bool,
    ) -> CommResponse:
        """
        Handles a registration call.
        """

        try:
            self._validate_registration(is_from_dev_server)

            with httpx.Client() as client:
                res = client.send(
                    self._build_registration_request(app_url),
                )

            return self._parse_registration_response(res)
        except errors.InternalError as err:
            return CommResponse.from_internal_error(err, self._framework)

    def _validate_registration(self, is_from_dev_server: bool) -> None:
        if is_from_dev_server and self._is_production:
            raise errors.DevServerRegistrationNotAllowed(
                "Dev Server registration not allowed in production mode"
            )
