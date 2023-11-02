from __future__ import annotations

import http
import json
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
    result,
    transforms,
    types,
)


class CommResponse:
    def __init__(
        self,
        *,
        body: types.Serializable = None,
        headers: dict[str, str],
        status_code: int = http.HTTPStatus.OK.value,
    ) -> None:
        self.headers = headers
        self.body = body
        self.status_code = status_code

    @property
    def is_success(self) -> bool:
        return self.status_code < 400

    @classmethod
    def from_call_result(
        cls,
        logger: logging.Logger,
        framework: const.Framework,
        call_res: execution.CallResult,
    ) -> CommResponse:
        headers = {
            **net.create_headers(framework=framework),
            const.HeaderKey.SERVER_TIMING.value: "handler",
        }

        if execution.is_step_call_responses(call_res):
            out: list[dict[str, object]] = []
            for item in call_res:
                match item.to_dict():
                    case result.Ok(d):
                        out.append(d)
                    case result.Err(err):
                        return cls.from_error(
                            logger,
                            framework,
                            err,
                        )

            return cls(
                body=transforms.prep_body(out),
                headers=headers,
                status_code=http.HTTPStatus.PARTIAL_CONTENT.value,
            )

        if isinstance(call_res, execution.CallError):
            logger.error(call_res.stack)

            match call_res.to_dict():
                case result.Ok(d):
                    body = transforms.prep_body(d)
                case result.Err(err):
                    return cls.from_error(
                        logger,
                        framework,
                        err,
                    )

            if call_res.is_retriable is False:
                headers[const.HeaderKey.NO_RETRY.value] = "true"

            return cls(
                body=body,
                headers=headers,
                status_code=http.HTTPStatus.INTERNAL_SERVER_ERROR.value,
            )

        if isinstance(call_res, execution.FunctionCallResponse):
            return cls(
                body=call_res.data,
                headers=headers,
            )

        return cls.from_error(
            logger,
            framework,
            errors.UnknownError("unknown call result"),
        )

    @classmethod
    def from_error(
        cls,
        logger: logging.Logger,
        framework: const.Framework,
        err: Exception,
    ) -> CommResponse:
        code: str | None = None
        status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR.value
        if isinstance(err, errors.InternalError):
            code = err.code.value
            status_code = err.status_code

        if code:
            logger.error(f"{code}: {str(err)}")
        else:
            logger.error(f"_{str(err)}_")

        return cls(
            body={
                "code": code,
                "message": str(err),
            },
            headers=net.create_headers(framework=framework),
            status_code=status_code,
        )


class CommHandler:
    _base_url: str
    _client: client_lib.Inngest
    _fns: dict[str, function.Function]
    _framework: const.Framework
    _is_production: bool
    _logger: logging.Logger
    _signing_key: str | None

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: client_lib.Inngest,
        framework: const.Framework,
        functions: list[function.Function],
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
    ) -> result.Result[httpx.Request, Exception]:
        registration_url = urllib.parse.urljoin(
            self._api_origin,
            "/fn/register",
        )

        match self.get_function_configs(app_url):
            case result.Ok(fn_configs):
                pass
            case result.Err(err):
                return result.Err(err)

        match registration.RegisterRequest(
            app_name=self._client.app_id,
            deploy_type=registration.DeployType.PING,
            framework=self._framework,
            functions=fn_configs,
            sdk=f"{const.LANGUAGE}:v{const.VERSION}",
            url=app_url,
            v="0.1",
        ).to_dict():
            case result.Ok(body):
                body = transforms.prep_body(body)
            case result.Err(err):
                return result.Err(err)

        headers = net.create_headers(framework=self._framework)
        if self._signing_key:
            headers[
                "Authorization"
            ] = f"Bearer {transforms.hash_signing_key(self._signing_key)}"

        return result.Ok(
            httpx.Client().build_request(
                "POST",
                registration_url,
                headers=headers,
                json=body,
                timeout=30,
            )
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

        # No memoized data means we're calling the function for the first time.
        if len(call.steps.keys()) == 0:
            self._client.middleware.before_run_execution_sync()

        comm_res: CommResponse

        validation_res = req_sig.validate(self._signing_key)
        if result.is_err(validation_res):
            err = validation_res.err_value
            extra = {}
            if isinstance(err, errors.InternalError):
                extra["code"] = err.code
            self._logger.error(err, extra=extra)
            comm_res = CommResponse.from_error(
                self._logger,
                self._framework,
                err,
            )
        else:
            match self._get_function(fn_id):
                case result.Ok(fn):
                    call_res = await fn.call(call, self._client, fn_id)

                    if isinstance(call_res, execution.FunctionCallResponse):
                        # Only call this hook if we get a return at the function
                        # level.
                        self._client.middleware.after_run_execution_sync()

                    comm_res = CommResponse.from_call_result(
                        self._logger,
                        self._framework,
                        call_res,
                    )
                case result.Err(err):
                    extra = {}
                    if isinstance(err, errors.InternalError):
                        extra["code"] = err.code
                    self._logger.error(err, extra=extra)
                    comm_res = CommResponse.from_error(
                        self._logger,
                        self._framework,
                        err,
                    )

        self._client.middleware.before_response_sync()
        return comm_res

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

        # No memoized data means we're calling the function for the first time.
        if len(call.steps.keys()) == 0:
            self._client.middleware.before_run_execution_sync()

        comm_res: CommResponse

        validation_res = req_sig.validate(self._signing_key)
        if result.is_err(validation_res):
            err = validation_res.err_value
            extra = {}
            if isinstance(err, errors.InternalError):
                extra["code"] = err.code
            self._logger.error(err, extra=extra)
            comm_res = CommResponse.from_error(
                self._logger,
                self._framework,
                err,
            )
        else:
            match self._get_function(fn_id):
                case result.Ok(fn):
                    call_res = fn.call_sync(call, self._client, fn_id)

                    if isinstance(call_res, execution.FunctionCallResponse):
                        # Only call this hook if we get a return at the function
                        # level.
                        self._client.middleware.after_run_execution_sync()

                    comm_res = CommResponse.from_call_result(
                        self._logger,
                        self._framework,
                        call_res,
                    )
                case result.Err(err):
                    extra = {}
                    if isinstance(err, errors.InternalError):
                        extra["code"] = err.code
                    self._logger.error(err, extra=extra)
                    comm_res = CommResponse.from_error(
                        self._logger,
                        self._framework,
                        err,
                    )

        self._client.middleware.before_response_sync()
        return comm_res

    def _get_function(
        self, fn_id: str
    ) -> result.Result[function.Function, Exception]:
        # Look for the function ID in the list of user functions, but also
        # look for it in the list of on_failure functions.
        for _fn in self._fns.values():
            if _fn.get_id() == fn_id:
                return result.Ok(_fn)
            if _fn.on_failure_fn_id == fn_id:
                return result.Ok(_fn)

        return result.Err(errors.MissingFunction(f"function {fn_id} not found"))

    def get_function_configs(
        self,
        app_url: str,
    ) -> result.Result[list[function_config.FunctionConfig], Exception]:
        configs: list[function_config.FunctionConfig] = []
        for fn in self._fns.values():
            config = fn.get_config(app_url)
            configs.append(config.main)

            if config.on_failure is not None:
                configs.append(config.on_failure)

        if len(configs) == 0:
            return result.Err(errors.InvalidConfig("no functions found"))
        return result.Ok(configs)

    def inspect(self, server_kind: const.ServerKind | None) -> CommResponse:
        """
        Used by Dev Server to discover apps.
        """

        if server_kind == const.ServerKind.DEV_SERVER and self._is_production:
            # Tell Dev Server to leave the app alone since it's in production
            # mode.
            return CommResponse(
                body=json.dumps({}),
                headers={},
                status_code=403,
            )

        return CommResponse(
            body=json.dumps({}),
            headers=net.create_headers(framework=self._framework),
            status_code=200,
        )

    def _parse_registration_response(
        self,
        server_res: httpx.Response,
    ) -> CommResponse:
        try:
            server_res_body = server_res.json()
        except Exception:
            return CommResponse.from_error(
                self._logger,
                self._framework,
                errors.RegistrationError("response is not valid JSON"),
            )

        if not isinstance(server_res_body, dict):
            return CommResponse.from_error(
                self._logger,
                self._framework,
                errors.RegistrationError("response is not an object"),
            )

        if server_res.status_code < 400:
            return CommResponse(
                body=server_res_body,
                headers=net.create_headers(framework=self._framework),
                status_code=server_res.status_code,
            )

        msg = server_res_body.get("error")
        if not isinstance(msg, str):
            msg = "registration failed"
        comm_res = CommResponse.from_error(
            self._logger,
            self._framework,
            errors.RegistrationError(msg.strip()),
        )
        comm_res.status_code = server_res.status_code
        return comm_res

    async def register(
        self,
        *,
        app_url: str,
        server_kind: const.ServerKind | None,
    ) -> CommResponse:
        """
        Handles a registration call.
        """

        match self._validate_registration(server_kind):
            case result.Ok(_):
                pass
            case result.Err(err):
                self._logger.error(err)
                return CommResponse.from_error(
                    self._logger,
                    self._framework,
                    err,
                )

        async with httpx.AsyncClient() as client:
            match self._build_registration_request(app_url):
                case result.Ok(req):
                    res = self._parse_registration_response(
                        await client.send(req)
                    )
                case result.Err(err):
                    self._logger.error(err)
                    return CommResponse.from_error(
                        self._logger,
                        self._framework,
                        err,
                    )

        return res

    def register_sync(
        self,
        *,
        app_url: str,
        server_kind: const.ServerKind | None,
    ) -> CommResponse:
        """
        Handles a registration call.
        """

        match self._validate_registration(server_kind):
            case result.Ok(_):
                pass
            case result.Err(err):
                self._logger.error(err)
                return CommResponse.from_error(
                    self._logger,
                    self._framework,
                    err,
                )

        with httpx.Client() as client:
            match self._build_registration_request(app_url):
                case result.Ok(req):
                    res = self._parse_registration_response(client.send(req))
                case result.Err(err):
                    self._logger.error(err)
                    return CommResponse.from_error(
                        self._logger,
                        self._framework,
                        err,
                    )

        return res

    def _validate_registration(
        self,
        server_kind: const.ServerKind | None,
    ) -> result.Result[None, Exception]:
        if server_kind == const.ServerKind.DEV_SERVER and self._is_production:
            return result.Err(
                errors.DevServerRegistrationNotAllowed(
                    "Dev Server registration not allowed in production mode"
                )
            )
        return result.Ok(None)
