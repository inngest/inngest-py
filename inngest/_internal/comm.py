from __future__ import annotations

import asyncio
import http
import os
import typing
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
    step_lib,
    transforms,
    types,
)


class _ErrorData(types.BaseModel):
    code: const.ErrorCode
    message: str
    name: str
    stack: typing.Optional[str]

    @classmethod
    def from_error(cls, err: Exception) -> _ErrorData:
        if isinstance(err, errors.Error):
            code = err.code
            message = err.message
            name = err.name
            stack = err.stack
        else:
            code = const.ErrorCode.UNKNOWN
            message = str(err)
            name = type(err).__name__
            stack = transforms.get_traceback(err)

        return cls(
            code=code,
            message=message,
            name=name,
            stack=stack,
        )


def _prep_call_result(
    call_res: execution.CallResult,
) -> types.MaybeError[object]:
    """
    Convert a CallResult to the shape the Inngest Server expects. For step-level
    results this is a dict and for function-level results this is the output or
    error.
    """

    if call_res.step is not None:
        d = call_res.step.to_dict()
        if isinstance(d, Exception):
            # Unreachable
            return d
    else:
        d = {}

    if call_res.error is not None:
        e = _ErrorData.from_error(call_res.error).to_dict()
        if isinstance(e, Exception):
            return e
        d["error"] = e

    if call_res.output is not types.empty_sentinel:
        err = transforms.dump_json(call_res.output)
        if isinstance(err, Exception):
            msg = "returned unserializable data"
            if call_res.step is not None:
                msg = f'"{call_res.step.display_name}" {msg}'

            return errors.OutputUnserializableError(msg)

        d["data"] = call_res.output

    is_function_level = call_res.step is None
    if is_function_level:
        # Don't nest function-level results
        return d.get("error") or d.get("data")

    return d


class CommResponse:
    def __init__(
        self,
        *,
        body: object = None,
        headers: typing.Optional[dict[str, str]] = None,
        status_code: int = http.HTTPStatus.OK.value,
    ) -> None:
        self.headers = headers or {}
        self.body = body
        self.status_code = status_code

    @classmethod
    def from_call_result(
        cls,
        logger: types.Logger,
        call_res: execution.CallResult,
    ) -> CommResponse:
        headers = {
            const.HeaderKey.SERVER_TIMING.value: "handler",
        }

        if call_res.multi:
            multi_body: list[object] = []
            for item in call_res.multi:
                d = _prep_call_result(item)
                if isinstance(d, Exception):
                    return cls.from_error(logger, d)
                multi_body.append(d)

                if item.error is not None:
                    if errors.is_retriable(item.error) is False:
                        headers[const.HeaderKey.NO_RETRY.value] = "true"

            return cls(
                body=multi_body,
                headers=headers,
                status_code=http.HTTPStatus.PARTIAL_CONTENT.value,
            )

        body = _prep_call_result(call_res)
        status_code = http.HTTPStatus.OK.value
        if isinstance(body, Exception):
            return cls.from_error(logger, body)

        if call_res.error is not None:
            status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR.value
            if errors.is_retriable(call_res.error) is False:
                headers[const.HeaderKey.NO_RETRY.value] = "true"

            if isinstance(call_res.error, errors.RetryAfterError):
                headers[
                    const.HeaderKey.RETRY_AFTER.value
                ] = transforms.to_iso_utc(call_res.error.retry_after)

        return cls(
            body=body,
            headers=headers,
            status_code=status_code,
        )

    @classmethod
    def from_error(
        cls,
        logger: types.Logger,
        err: Exception,
        status: http.HTTPStatus = http.HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> CommResponse:
        code: typing.Optional[str] = None
        if isinstance(err, errors.Error):
            code = err.code.value
        else:
            code = const.ErrorCode.UNKNOWN.value

        if errors.is_quiet(err) is False:
            logger.error(f"{code}: {err!s}")

        return cls(
            body={
                "code": code,
                "message": str(err),
                "name": type(err).__name__,
            },
            status_code=status.value,
        )

    @classmethod
    def from_error_code(
        cls,
        code: const.ErrorCode,
        message: str,
        status: http.HTTPStatus = http.HTTPStatus.INTERNAL_SERVER_ERROR,
    ) -> CommResponse:
        return cls(
            body={
                "code": code.value,
                "message": message,
            },
            status_code=status.value,
        )


class CommHandler:
    _base_url: str
    _client: client_lib.Inngest
    _fns: dict[str, function.Function]
    _framework: const.Framework
    _mode: const.ServerKind
    _signing_key: typing.Optional[str]
    _signing_key_fallback: typing.Optional[str]

    def __init__(
        self,
        *,
        api_base_url: typing.Optional[str] = None,
        client: client_lib.Inngest,
        framework: const.Framework,
        functions: list[function.Function],
    ) -> None:
        self._client = client

        self._mode = client._mode

        api_base_url = api_base_url or os.getenv(
            const.EnvKey.API_BASE_URL.value
        )
        if api_base_url is None:
            if self._mode == const.ServerKind.DEV_SERVER:
                api_base_url = const.DEV_SERVER_ORIGIN
            else:
                api_base_url = const.DEFAULT_API_ORIGIN

        try:
            self._api_origin = net.parse_url(api_base_url)
        except Exception as err:
            raise errors.URLInvalidError() from err

        self._fns = {fn.get_id(): fn for fn in functions}
        self._framework = framework

        signing_key = client.signing_key
        if signing_key is None:
            if self._client.is_production:
                signing_key = os.getenv(const.EnvKey.SIGNING_KEY.value)
                if signing_key is None:
                    self._client.logger.error("missing signing key")
                    raise errors.SigningKeyMissingError()
        self._signing_key = signing_key

        self._signing_key_fallback = client.signing_key_fallback

    def _build_registration_request(
        self,
        *,
        app_url: str,
        server_kind: typing.Optional[const.ServerKind],
        sync_id: typing.Optional[str],
    ) -> types.MaybeError[httpx.Request]:
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

        headers = net.create_headers(
            env=self._client.env,
            framework=self._framework,
            server_kind=server_kind,
        )

        params = {}
        if sync_id is not None:
            params[const.QueryParamKey.SYNC_ID.value] = sync_id

        return self._client._http_client_sync.build_request(
            "POST",
            registration_url,
            headers=headers,
            json=transforms.deep_strip_none(body),
            params=params,
            timeout=30,
        )

    async def call_function(
        self,
        *,
        call: execution.Call,
        fn_id: str,
        raw_request: object,
        req_sig: net.RequestSignature,
        target_hashed_id: str,
    ) -> CommResponse:
        """Handle a function call from the Executor."""

        if target_hashed_id == execution.UNSPECIFIED_STEP_ID:
            target_step_id = None
        else:
            target_step_id = target_hashed_id

        middleware = middleware_lib.MiddlewareManager.from_client(
            self._client,
            raw_request,
        )

        # Validate the request signature.
        err = req_sig.validate(
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(err, Exception):
            return await self._respond(err)

        # Get the function we should call.
        fn = self._get_function(fn_id)
        if isinstance(fn, Exception):
            return await self._respond(fn)

        events = call.events
        steps = call.steps
        if call.use_api:
            # Putting the batch and memoized steps in the request would make it
            # to big, so the Executor is telling the SDK to fetch them from the
            # API

            fetched_events, fetched_steps = await asyncio.gather(
                self._client._get_batch(call.ctx.run_id),
                self._client._get_steps(call.ctx.run_id),
            )
            if isinstance(fetched_events, Exception):
                return await self._respond(fetched_events)
            events = fetched_events
            if isinstance(fetched_steps, Exception):
                return await self._respond(fetched_steps)
            steps = fetched_steps
        if events is None:
            # Should be unreachable. The Executor should always either send the
            # batch or tell the SDK to fetch the batch

            return await self._respond(Exception("events not in request"))

        call_res = await fn.call(
            self._client,
            function.Context(
                attempt=call.ctx.attempt,
                event=call.event,
                events=events,
                logger=self._client.logger,
                run_id=call.ctx.run_id,
            ),
            fn_id,
            middleware,
            step_lib.StepMemos.from_raw(steps),
            target_step_id,
        )

        return await self._respond(call_res)

    def call_function_sync(
        self,
        *,
        call: execution.Call,
        fn_id: str,
        raw_request: object,
        req_sig: net.RequestSignature,
        target_hashed_id: str,
    ) -> CommResponse:
        """Handle a function call from the Executor."""

        if target_hashed_id == execution.UNSPECIFIED_STEP_ID:
            target_step_id = None
        else:
            target_step_id = target_hashed_id

        middleware = middleware_lib.MiddlewareManager.from_client(
            self._client,
            raw_request,
        )

        # Validate the request signature.
        err = req_sig.validate(
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(err, Exception):
            return self._respond_sync(err)

        # Get the function we should call.
        fn = self._get_function(fn_id)
        if isinstance(fn, Exception):
            return self._respond_sync(fn)

        events = call.events
        steps = call.steps
        if call.use_api:
            # Putting the batch and memoized steps in the request would make it
            # to big, so the Executor is telling the SDK to fetch them from the
            # API

            fetched_events = self._client._get_batch_sync(call.ctx.run_id)
            if isinstance(fetched_events, Exception):
                return self._respond_sync(fetched_events)
            events = fetched_events

            fetched_steps = self._client._get_steps_sync(call.ctx.run_id)
            if isinstance(fetched_steps, Exception):
                return self._respond_sync(fetched_steps)
            steps = fetched_steps
        if events is None:
            # Should be unreachable. The Executor should always either send the
            # batch or tell the SDK to fetch the batch

            return self._respond_sync(Exception("events not in request"))

        call_res = fn.call_sync(
            self._client,
            function.Context(
                attempt=call.ctx.attempt,
                event=call.event,
                events=events,
                logger=self._client.logger,
                run_id=call.ctx.run_id,
            ),
            fn_id,
            middleware,
            step_lib.StepMemos.from_raw(steps),
            target_step_id,
        )

        return self._respond_sync(call_res)

    def _get_function(self, fn_id: str) -> types.MaybeError[function.Function]:
        # Look for the function ID in the list of user functions, but also
        # look for it in the list of on_failure functions.
        for _fn in self._fns.values():
            if _fn.get_id() == fn_id:
                return _fn
            if _fn.on_failure_fn_id == fn_id:
                return _fn

        # If we didn't find the function ID, it might be because the function ID
        # in the request uses the old format that didn't include the app ID.
        # We'll prefix the function ID with the app ID and try again. This logic
        # can be deleted when no one is using Python SDK versions below 0.3.0
        # anymore.
        app_and_fn_id = f"{self._client.app_id}-{fn_id}"
        for _fn in self._fns.values():
            if _fn.get_id() == app_and_fn_id:
                return _fn
            if _fn.on_failure_fn_id == app_and_fn_id:
                return _fn

        return errors.FunctionNotFoundError(f"function {fn_id} not found")

    def get_function_configs(
        self,
        app_url: str,
    ) -> types.MaybeError[list[function_config.FunctionConfig]]:
        configs: list[function_config.FunctionConfig] = []
        for fn in self._fns.values():
            config = fn.get_config(app_url)
            configs.append(config.main)

            if config.on_failure is not None:
                configs.append(config.on_failure)

        if len(configs) == 0:
            return errors.FunctionConfigInvalidError("no functions found")
        return configs

    def inspect(
        self,
        *,
        req_sig: net.RequestSignature,
        serve_origin: typing.Optional[str],
        serve_path: typing.Optional[str],
        server_kind: typing.Optional[const.ServerKind],
    ) -> CommResponse:
        """Handle Dev Server's auto-discovery."""

        if server_kind is not None and server_kind != self._mode:
            # Tell Dev Server to leave the app alone since it's in production
            # mode.
            return CommResponse(
                body={},
                headers={},
                status_code=403,
            )

        # Validate the request signature.
        err = req_sig.validate(
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if self._client._mode != const.ServerKind.CLOUD or isinstance(
            err, Exception
        ):
            authentication_succeeded = None
            if isinstance(err, Exception):
                authentication_succeeded = False

            body = _UnauthenticatedIntrospection(
                authentication_succeeded=authentication_succeeded,
                function_count=len(self._fns),
                has_event_key=self._client.event_key is not None,
                has_signing_key=self._signing_key is not None,
                has_signing_key_fallback=self._signing_key_fallback is not None,
                mode=self._mode,
            )
        else:
            event_key_hash = (
                transforms.hash_event_key(self._client.event_key)
                if self._client.event_key
                else None
            )

            signing_key_hash = (
                transforms.hash_signing_key(self._signing_key)
                if self._signing_key
                else None
            )

            signing_key_fallback_hash = (
                transforms.hash_signing_key(self._signing_key_fallback)
                if self._signing_key_fallback
                else None
            )

            body = _AuthenticatedIntrospection(
                api_origin=self._client.api_origin,
                app_id=self._client.app_id,
                authentication_succeeded=True,
                env=self._client.env,
                event_api_origin=self._client.event_api_origin,
                event_key_hash=event_key_hash,
                framework=self._framework.value,
                function_count=len(self._fns),
                has_event_key=self._client.event_key is not None,
                has_signing_key=self._signing_key is not None,
                has_signing_key_fallback=self._signing_key_fallback is not None,
                mode=self._mode,
                serve_origin=serve_origin,
                serve_path=serve_path,
                signing_key_fallback_hash=signing_key_fallback_hash,
                signing_key_hash=signing_key_hash,
            )

        body_json = body.to_dict()
        if isinstance(body, Exception):
            body_json = {
                "error": "failed to serialize inspection data",
            }

        return CommResponse(
            body=body_json,
            headers=net.create_headers(
                env=self._client.env,
                framework=self._framework,
                server_kind=server_kind,
            ),
            status_code=200,
        )

    def _parse_registration_response(
        self,
        server_res: httpx.Response,
        server_kind: typing.Optional[const.ServerKind],
    ) -> CommResponse:
        try:
            server_res_body = server_res.json()
        except Exception:
            return CommResponse.from_error(
                self._client.logger,
                errors.RegistrationFailedError("response is not valid JSON"),
            )

        if not isinstance(server_res_body, dict):
            return CommResponse.from_error(
                self._client.logger,
                errors.RegistrationFailedError("response is not an object"),
            )

        if server_res.status_code < 400:
            return CommResponse(
                body=server_res_body,
                headers=net.create_headers(
                    env=self._client.env,
                    framework=self._framework,
                    server_kind=server_kind,
                ),
                status_code=http.HTTPStatus.OK,
            )

        msg = server_res_body.get("error")
        if not isinstance(msg, str):
            msg = "registration failed"
        comm_res = CommResponse.from_error(
            self._client.logger,
            errors.RegistrationFailedError(msg.strip()),
        )
        comm_res.status_code = server_res.status_code
        return comm_res

    async def register(
        self,
        *,
        app_url: str,
        server_kind: typing.Optional[const.ServerKind],
        sync_id: typing.Optional[str],
    ) -> CommResponse:
        """Handle a registration call."""

        comm_res = self._validate_registration(server_kind)
        if comm_res is not None:
            return comm_res

        req = self._build_registration_request(
            app_url=app_url,
            server_kind=server_kind,
            sync_id=sync_id,
        )
        if isinstance(req, Exception):
            return CommResponse.from_error(self._client.logger, req)

        res = await net.fetch_with_auth_fallback(
            self._client._http_client,
            self._client._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )

        return self._parse_registration_response(
            res,
            server_kind,
        )

    def register_sync(
        self,
        *,
        app_url: str,
        server_kind: typing.Optional[const.ServerKind],
        sync_id: typing.Optional[str],
    ) -> CommResponse:
        """Handle a registration call."""

        comm_res = self._validate_registration(server_kind)
        if comm_res is not None:
            return comm_res

        req = self._build_registration_request(
            app_url=app_url,
            server_kind=server_kind,
            sync_id=sync_id,
        )
        if isinstance(req, Exception):
            return CommResponse.from_error(self._client.logger, req)

        res = net.fetch_with_auth_fallback_sync(
            self._client._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )

        return self._parse_registration_response(
            res,
            server_kind,
        )

    async def _respond(
        self,
        value: typing.Union[execution.CallResult, Exception],
    ) -> CommResponse:
        if isinstance(value, Exception):
            return CommResponse.from_error(self._client.logger, value)

        return CommResponse.from_call_result(self._client.logger, value)

    def _respond_sync(
        self,
        value: typing.Union[execution.CallResult, Exception],
    ) -> CommResponse:
        if isinstance(value, Exception):
            return CommResponse.from_error(self._client.logger, value)

        return CommResponse.from_call_result(self._client.logger, value)

    def _validate_registration(
        self,
        server_kind: typing.Optional[const.ServerKind],
    ) -> typing.Optional[CommResponse]:
        if server_kind is not None and server_kind != self._mode:
            msg: str
            if server_kind == const.ServerKind.DEV_SERVER:
                msg = "Sync rejected since it's from a Dev Server but expected Cloud"
            else:
                msg = "Sync rejected since it's from Cloud but expected Dev Server"

            self._client.logger.error(msg)
            return CommResponse.from_error_code(
                const.ErrorCode.SERVER_KIND_MISMATCH,
                msg,
                http.HTTPStatus.BAD_REQUEST,
            )

        return None


class _UnauthenticatedIntrospection(types.BaseModel):
    schema_version: str = "2024-05-24"

    authentication_succeeded: typing.Optional[bool]
    function_count: int
    has_event_key: bool
    has_signing_key: bool
    has_signing_key_fallback: bool
    mode: const.ServerKind


class _AuthenticatedIntrospection(_UnauthenticatedIntrospection):
    api_origin: str
    app_id: str
    authentication_succeeded: bool = True
    env: typing.Optional[str]
    event_api_origin: str
    event_key_hash: typing.Optional[str]
    framework: str
    sdk_language: str = const.LANGUAGE
    sdk_version: str = const.VERSION
    serve_origin: typing.Optional[str]
    serve_path: typing.Optional[str]
    signing_key_fallback_hash: typing.Optional[str]
    signing_key_hash: typing.Optional[str]
