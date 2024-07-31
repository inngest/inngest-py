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
    execution_lib,
    function,
    middleware_lib,
    net,
    server_lib,
    step_lib,
    transforms,
    types,
)

from .models import (
    AuthenticatedInspection,
    CommRequest,
    CommResponse,
    UnauthenticatedInspection,
)
from .utils import parse_query_params, wrap_handler, wrap_handler_sync


class CommHandler:
    _base_url: str
    _client: client_lib.Inngest
    _fns: dict[str, function.Function]
    _framework: server_lib.Framework
    _mode: server_lib.ServerKind
    _signing_key: typing.Optional[str]
    _signing_key_fallback: typing.Optional[str]

    def __init__(
        self,
        *,
        client: client_lib.Inngest,
        framework: server_lib.Framework,
        functions: list[function.Function],
    ) -> None:
        self._client = client
        self._mode = client._mode
        self._api_origin = client.api_origin
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

    def _build_register_request(
        self,
        *,
        app_url: str,
        server_kind: typing.Optional[server_lib.ServerKind],
        sync_id: typing.Optional[str],
    ) -> types.MaybeError[httpx.Request]:
        registration_url = urllib.parse.urljoin(
            self._api_origin,
            "/fn/register",
        )

        fn_configs = self.get_function_configs(app_url)
        if isinstance(fn_configs, Exception):
            return fn_configs

        body = server_lib.SynchronizeRequest(
            app_name=self._client.app_id,
            deploy_type=server_lib.DeployType.PING,
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
            params[server_lib.QueryParamKey.SYNC_ID.value] = sync_id

        return self._client._http_client_sync.build_request(
            "POST",
            registration_url,
            headers=headers,
            json=transforms.deep_strip_none(body),
            params=params,
            timeout=30,
        )

    @wrap_handler
    async def post(
        self,
        req: CommRequest,
        request_signing_key: types.MaybeError[typing.Optional[str]],
    ) -> typing.Union[CommResponse, Exception]:
        """Handle a function call from the Executor."""

        headers = net.normalize_headers(req.headers)

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None

        middleware = middleware_lib.MiddlewareManager.from_client(
            self._client,
            req.raw_request,
        )

        # Validate the request signature.
        err = net.validate_request(
            body=req.body,
            headers=headers,
            mode=self._client._mode,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(err, Exception):
            return err

        request = server_lib.ServerRequest.from_raw(req.body)
        if isinstance(request, Exception):
            return request

        params = parse_query_params(req.query_params)
        if isinstance(params, Exception):
            return params
        if params.fn_id is None:
            return errors.QueryParamMissingError(
                server_lib.QueryParamKey.FUNCTION_ID.value
            )

        # Get the function we should call.
        fn = self._get_function(params.fn_id)
        if isinstance(fn, Exception):
            return fn

        events = request.events
        steps = request.steps
        if request.use_api:
            # Putting the batch and memoized steps in the request would make it
            # to big, so the Executor is telling the SDK to fetch them from the
            # API

            fetched_events, fetched_steps = await asyncio.gather(
                self._client._get_batch(request.ctx.run_id),
                self._client._get_steps(request.ctx.run_id),
            )
            if isinstance(fetched_events, Exception):
                return fetched_events
            events = fetched_events
            if isinstance(fetched_steps, Exception):
                return fetched_steps
            steps = fetched_steps
        if events is None:
            # Should be unreachable. The Executor should always either send the
            # batch or tell the SDK to fetch the batch

            return Exception("events not in request")
        call_res = await fn.call(
            self._client,
            execution_lib.Context(
                attempt=request.ctx.attempt,
                event=request.event,
                events=events,
                logger=self._client.logger,
                run_id=request.ctx.run_id,
            ),
            params.fn_id,
            middleware,
            request,
            step_lib.StepMemos.from_raw(steps),
            params.step_id,
        )

        return CommResponse.from_call_result(
            self._client.logger,
            call_res,
            self._client.env,
            self._framework,
            server_kind,
        )

    @wrap_handler_sync
    def post_sync(
        self,
        req: CommRequest,
        # *,
        # body: bytes,
        # headers: typing.Union[dict[str, str], dict[str, str]],
        # query_params: typing.Union[dict[str, str], dict[str, list[str]]],
        # raw_request: object,
        request_signing_key: types.MaybeError[typing.Optional[str]],
        # serve_origin: typing.Optional[str],
        # serve_path: typing.Optional[str],
    ) -> typing.Union[CommResponse, Exception]:
        """Handle a function call from the Executor."""

        server_kind = transforms.get_server_kind(req.headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None

        middleware = middleware_lib.MiddlewareManager.from_client(
            self._client,
            req.raw_request,
        )

        request = server_lib.ServerRequest.from_raw(req.body)
        if isinstance(request, Exception):
            return request

        params = parse_query_params(req.query_params)
        if isinstance(params, Exception):
            return params
        if params.fn_id is None:
            return errors.QueryParamMissingError(
                server_lib.QueryParamKey.FUNCTION_ID.value
            )

        # Get the function we should call.
        fn = self._get_function(params.fn_id)
        if isinstance(fn, Exception):
            return fn

        events = request.events
        steps = request.steps
        if request.use_api:
            # Putting the batch and memoized steps in the request would make it
            # to big, so the Executor is telling the SDK to fetch them from the
            # API

            fetched_events = self._client._get_batch_sync(request.ctx.run_id)
            if isinstance(fetched_events, Exception):
                return fetched_events
            events = fetched_events

            fetched_steps = self._client._get_steps_sync(request.ctx.run_id)
            if isinstance(fetched_steps, Exception):
                return fetched_steps
            steps = fetched_steps
        if events is None:
            # Should be unreachable. The Executor should always either send the
            # batch or tell the SDK to fetch the batch

            return Exception("events not in request")

        call_res = fn.call_sync(
            self._client,
            execution_lib.Context(
                attempt=request.ctx.attempt,
                event=request.event,
                events=events,
                logger=self._client.logger,
                run_id=request.ctx.run_id,
            ),
            params.fn_id,
            middleware,
            request,
            step_lib.StepMemos.from_raw(steps),
            params.step_id,
        )

        return CommResponse.from_call_result(
            self._client.logger,
            call_res,
            self._client.env,
            self._framework,
            server_kind,
        )

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
    ) -> types.MaybeError[list[server_lib.FunctionConfig]]:
        configs: list[server_lib.FunctionConfig] = []
        for fn in self._fns.values():
            config = fn.get_config(app_url)
            configs.append(config.main)

            if config.on_failure is not None:
                configs.append(config.on_failure)

        if len(configs) == 0:
            return errors.FunctionConfigInvalidError("no functions found")
        return configs

    @wrap_handler_sync
    def get_sync(
        self,
        req: CommRequest,
        request_signing_key: types.MaybeError[typing.Optional[str]],
    ) -> types.MaybeError[CommResponse]:
        """Handle Dev Server's auto-discovery."""

        server_kind = transforms.get_server_kind(req.headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None

        if server_kind is not None and server_kind != self._mode:
            # Tell Dev Server to leave the app alone since it's in production
            # mode.
            return CommResponse(
                body={},
                status_code=403,
            )

        res_body: typing.Union[
            AuthenticatedInspection, UnauthenticatedInspection
        ]

        is_signed_and_valid = isinstance(request_signing_key, str)
        # Validate the request signature.
        err = net.validate_request(
            body=req.body,
            headers=req.headers,
            mode=self._client._mode,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if (
            self._client._mode != server_lib.ServerKind.CLOUD
            or is_signed_and_valid is False
        ):
            authentication_succeeded = None
            if isinstance(err, Exception):
                authentication_succeeded = False

            res_body = UnauthenticatedInspection(
                authentication_succeeded=authentication_succeeded,
                function_count=len(self._fns),
                has_event_key=self._client.event_key is not None,
                has_signing_key=self._signing_key is not None,
                has_signing_key_fallback=self._signing_key_fallback is not None,
                mode=self._mode,
            )
        elif is_signed_and_valid is True:
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

            res_body = AuthenticatedInspection(
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
                serve_origin=req.serve_origin,
                serve_path=req.serve_path,
                signing_key_fallback_hash=signing_key_fallback_hash,
                signing_key_hash=signing_key_hash,
            )

        body_json = res_body.to_dict()
        if isinstance(req.body, Exception):
            body_json = {
                "error": "failed to serialize inspection data",
            }

        return CommResponse(
            body=body_json,
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

    @wrap_handler
    async def put(
        self: CommHandler,
        req: CommRequest,
        request_signing_key: types.MaybeError[typing.Optional[str]],
    ) -> typing.Union[CommResponse, Exception]:
        """Handle a registration call."""

        headers = net.normalize_headers(req.headers)

        app_url = net.create_serve_url(
            request_url=req.request_url,
            serve_origin=req.serve_origin,
            serve_path=req.serve_path,
        )

        server_kind = transforms.get_server_kind(headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None

        comm_res = self._validate_registration(server_kind)
        if comm_res is not None:
            return comm_res

        params = parse_query_params(req.query_params)
        if isinstance(params, Exception):
            return params

        outgoing_req = self._build_register_request(
            app_url=app_url,
            server_kind=server_kind,
            sync_id=params.sync_id,
        )
        if isinstance(outgoing_req, Exception):
            return outgoing_req

        res = await net.fetch_with_auth_fallback(
            self._client._http_client,
            self._client._http_client_sync,
            outgoing_req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        return self._parse_registration_response(res)

    @wrap_handler_sync
    def put_sync(
        self: CommHandler,
        req: CommRequest,
        request_signing_key: types.MaybeError[typing.Optional[str]],
    ) -> typing.Union[CommResponse, Exception]:
        """Handle a registration call."""

        app_url = net.create_serve_url(
            request_url=req.request_url,
            serve_origin=req.serve_origin,
            serve_path=req.serve_path,
        )

        server_kind = transforms.get_server_kind(req.headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None

        comm_res = self._validate_registration(server_kind)
        if comm_res is not None:
            return comm_res

        params = parse_query_params(req.query_params)
        if isinstance(params, Exception):
            return params

        outgoing_req = self._build_register_request(
            app_url=app_url,
            server_kind=server_kind,
            sync_id=params.sync_id,
        )
        if isinstance(outgoing_req, Exception):
            return outgoing_req

        res = net.fetch_with_auth_fallback_sync(
            self._client._http_client_sync,
            outgoing_req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        return self._parse_registration_response(res)

    def _validate_registration(
        self,
        server_kind: typing.Optional[server_lib.ServerKind],
    ) -> typing.Optional[CommResponse]:
        if server_kind is not None and server_kind != self._mode:
            msg: str
            if server_kind == server_lib.ServerKind.DEV_SERVER:
                msg = "Sync rejected since it's from a Dev Server but expected Cloud"
            else:
                msg = "Sync rejected since it's from Cloud but expected Dev Server"

            self._client.logger.error(msg)
            return CommResponse.from_error_code(
                server_lib.ErrorCode.SERVER_KIND_MISMATCH,
                msg,
                http.HTTPStatus.BAD_REQUEST,
            )

        return None
