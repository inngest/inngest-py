from __future__ import annotations

import http
import json
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
    middleware_lib,
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
        body: bytes | None = None,
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
        logger: types.Logger,
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
                d = item.to_dict()
                if isinstance(d, Exception):
                    return cls.from_error(
                        logger,
                        framework,
                        errors.UnserializableOutput(
                            f'"{item.display_name}" returned unserializable data'
                        ),
                    )

                out.append(d)

            body = transforms.dump_json(transforms.prep_body(out))
            if isinstance(body, Exception):
                return cls.from_error(
                    logger,
                    framework,
                    body,
                )

            return cls(
                body=body.encode("utf-8"),
                headers=headers,
                status_code=http.HTTPStatus.PARTIAL_CONTENT.value,
            )

        if isinstance(call_res, execution.CallError):
            logger.error(call_res.stack)

            d = call_res.to_dict()
            if isinstance(d, Exception):
                return cls.from_error(
                    logger,
                    framework,
                    d,
                )

            body = transforms.dump_json(transforms.prep_body(d))
            if isinstance(body, Exception):
                return cls.from_error(
                    logger,
                    framework,
                    body,
                )

            if call_res.is_retriable is False:
                headers[const.HeaderKey.NO_RETRY.value] = "true"

            return cls(
                body=body.encode("utf-8"),
                headers=headers,
                status_code=http.HTTPStatus.INTERNAL_SERVER_ERROR.value,
            )

        if isinstance(call_res, execution.FunctionCallResponse):
            body = transforms.dump_json(transforms.prep_body(call_res.data))
            if isinstance(body, Exception):
                return cls.from_error(
                    logger,
                    framework,
                    body,
                )

            return cls(
                body=body.encode("utf-8"),
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
        logger: types.Logger,
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
            body=json.dumps(
                {
                    "code": code,
                    "message": str(err),
                    "name": type(err).__name__,
                }
            ).encode("utf-8"),
            headers=net.create_headers(framework=framework),
            status_code=status_code,
        )


class CommHandler:
    _base_url: str
    _client: client_lib.Inngest
    _fns: dict[str, function.Function]
    _framework: const.Framework
    _is_production: bool
    _signing_key: str | None

    def __init__(
        self,
        *,
        base_url: str | None = None,
        client: client_lib.Inngest,
        framework: const.Framework,
        functions: list[function.Function],
        signing_key: str | None = None,
    ) -> None:
        self._client = client

        self._is_production = client.is_production
        if self._is_production:
            self._client.logger.info("Running in production mode")
        else:
            self._client.logger.warning("Running in development mode")

        if not self._is_production:
            self._client.logger.info("Dev Server mode enabled")

        base_url = base_url or os.getenv(const.EnvKey.BASE_URL.value)
        if base_url is None:
            if not self._is_production:
                self._client.logger.info("Defaulting API origin to Dev Server")
                base_url = const.DEV_SERVER_ORIGIN
            else:
                base_url = const.DEFAULT_API_ORIGIN

        try:
            self._api_origin = net.parse_url(base_url)
        except Exception as err:
            raise errors.InvalidBaseURL() from err

        self._fns = {fn.get_id(): fn for fn in functions}
        self._framework = framework

        if signing_key is None:
            if self._client.is_production:
                signing_key = os.getenv(const.EnvKey.SIGNING_KEY.value)
                if signing_key is None:
                    self._client.logger.error("missing signing key")
                    raise errors.MissingSigningKey()
        self._signing_key = signing_key

    def _build_registration_request(
        self,
        app_url: str,
    ) -> result.MaybeError[httpx.Request]:
        registration_url = urllib.parse.urljoin(
            self._api_origin,
            "/fn/register",
        )

        fn_configs = self.get_function_configs(app_url)
        if isinstance(fn_configs, Exception):
            return fn_configs

        body = registration.RegisterRequest(
            app_name=self._client.app_id,
            deploy_type=registration.DeployType.PING,
            framework=self._framework,
            functions=fn_configs,
            sdk=f"{const.LANGUAGE}:v{const.VERSION}",
            url=app_url,
            v="0.1",
        ).to_dict()
        if isinstance(body, Exception):
            return body

        body = transforms.prep_body(body)
        if isinstance(body, Exception):
            return body

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

        middleware = middleware_lib.MiddlewareManager.from_client(self._client)

        # Validate the request signature.
        err = req_sig.validate(self._signing_key)
        if isinstance(err, Exception):
            return await self._respond(middleware, err)

        # Get the function we should call.
        fn = self._get_function(fn_id)
        if isinstance(fn, Exception):
            return await self._respond(middleware, fn)

        call_res = await fn.call(
            call,
            self._client,
            fn_id,
            execution.TransformableCallInput(logger=self._client.logger),
            middleware,
        )

        return await self._respond(middleware, call_res)

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

        middleware = middleware_lib.MiddlewareManager.from_client(self._client)

        # Validate the request signature.
        err = req_sig.validate(self._signing_key)
        if isinstance(err, Exception):
            return self._respond_sync(middleware, err)

        # Get the function we should call.
        fn = self._get_function(fn_id)
        if isinstance(fn, Exception):
            return self._respond_sync(middleware, fn)

        call_res = fn.call_sync(
            call,
            self._client,
            fn_id,
            execution.TransformableCallInput(logger=self._client.logger),
            middleware,
        )

        return self._respond_sync(middleware, call_res)

    def _get_function(self, fn_id: str) -> result.MaybeError[function.Function]:
        # Look for the function ID in the list of user functions, but also
        # look for it in the list of on_failure functions.
        for _fn in self._fns.values():
            if _fn.get_id() == fn_id:
                return _fn
            if _fn.on_failure_fn_id == fn_id:
                return _fn

        return errors.MissingFunction(f"function {fn_id} not found")

    def get_function_configs(
        self,
        app_url: str,
    ) -> result.MaybeError[list[function_config.FunctionConfig]]:
        configs: list[function_config.FunctionConfig] = []
        for fn in self._fns.values():
            config = fn.get_config(app_url)
            configs.append(config.main)

            if config.on_failure is not None:
                configs.append(config.on_failure)

        if len(configs) == 0:
            return errors.InvalidConfig("no functions found")
        return configs

    def inspect(self, server_kind: const.ServerKind | None) -> CommResponse:
        """
        Used by Dev Server to discover apps.
        """

        if server_kind == const.ServerKind.DEV_SERVER and self._is_production:
            # Tell Dev Server to leave the app alone since it's in production
            # mode.
            return CommResponse(
                body=json.dumps({}).encode("utf-8"),
                headers={},
                status_code=403,
            )

        return CommResponse(
            body=json.dumps({}).encode("utf-8"),
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
                self._client.logger,
                self._framework,
                errors.RegistrationError("response is not valid JSON"),
            )

        if not isinstance(server_res_body, dict):
            return CommResponse.from_error(
                self._client.logger,
                self._framework,
                errors.RegistrationError("response is not an object"),
            )

        if server_res.status_code < 400:
            return CommResponse(
                body=json.dumps(server_res_body).encode("utf-8"),
                headers=net.create_headers(framework=self._framework),
                status_code=server_res.status_code,
            )

        msg = server_res_body.get("error")
        if not isinstance(msg, str):
            msg = "registration failed"
        comm_res = CommResponse.from_error(
            self._client.logger,
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

        err = self._validate_registration(server_kind)
        if isinstance(err, Exception):
            return CommResponse.from_error(
                self._client.logger,
                self._framework,
                err,
            )

        async with httpx.AsyncClient() as client:
            req = self._build_registration_request(app_url)
            if isinstance(req, Exception):
                return CommResponse.from_error(
                    self._client.logger,
                    self._framework,
                    req,
                )

            return self._parse_registration_response(await client.send(req))

    def register_sync(
        self,
        *,
        app_url: str,
        server_kind: const.ServerKind | None,
    ) -> CommResponse:
        """
        Handles a registration call.
        """

        err = self._validate_registration(server_kind)
        if isinstance(err, Exception):
            return CommResponse.from_error(
                self._client.logger,
                self._framework,
                err,
            )

        with httpx.Client() as client:
            req = self._build_registration_request(app_url)
            if isinstance(req, Exception):
                return CommResponse.from_error(
                    self._client.logger,
                    self._framework,
                    req,
                )

            return self._parse_registration_response(client.send(req))

    async def _respond(
        self,
        middleware: middleware_lib.MiddlewareManager,
        value: execution.CallResult | Exception,
    ) -> CommResponse:
        err = await middleware.before_response()
        if isinstance(err, Exception):
            return CommResponse.from_error(
                self._client.logger,
                self._framework,
                err,
            )

        if isinstance(value, Exception):
            return CommResponse.from_error(
                self._client.logger,
                self._framework,
                value,
            )

        return CommResponse.from_call_result(
            self._client.logger,
            self._framework,
            value,
        )

    def _respond_sync(
        self,
        middleware: middleware_lib.MiddlewareManager,
        value: execution.CallResult | Exception,
    ) -> CommResponse:
        err = middleware.before_response_sync()
        if isinstance(err, Exception):
            return CommResponse.from_error(
                self._client.logger,
                self._framework,
                err,
            )

        if isinstance(value, Exception):
            return CommResponse.from_error(
                self._client.logger,
                self._framework,
                value,
            )

        return CommResponse.from_call_result(
            self._client.logger,
            self._framework,
            value,
        )

    def _validate_registration(
        self,
        server_kind: const.ServerKind | None,
    ) -> result.MaybeError[None]:
        if server_kind == const.ServerKind.DEV_SERVER and self._is_production:
            return errors.DevServerRegistrationNotAllowed(
                "Dev Server registration not allowed in production mode"
            )

        return None
