from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import functools
import http
import os
import typing
import urllib.parse

import httpx

from inngest._internal import (
    client_lib,
    const,
    env_lib,
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

from .models import CommRequest, CommResponse
from .utils import parse_query_params, wrap_handler, wrap_handler_sync


@dataclasses.dataclass
class ThreadPoolConfig:
    """
    Configuration for thread pools used to execute Inngest functions. This
    config is effectively ignored when using a synchronous HTTP framework.
    """

    pool: concurrent.futures.ThreadPoolExecutor

    # Whether to run async Inngest functions in the thread pool.
    enable_for_async_fns: bool = True

    # Whether to run sync Inngest functions in the thread pool.
    enable_for_sync_fns: bool = True


class CommHandler:
    _base_url: str
    _client: client_lib.Inngest
    _fns: dict[str, function.Function[typing.Any]]
    _framework: server_lib.Framework
    _mode: server_lib.ServerKind
    _signing_key: str | None
    _signing_key_fallback: str | None

    def __init__(
        self,
        *,
        client: client_lib.Inngest,
        framework: server_lib.Framework,
        functions: list[function.Function[typing.Any]],
        streaming: const.Streaming | None,
        thread_pool: ThreadPoolConfig | None = None,
    ) -> None:
        # In-band syncing is opt-out.
        self._allow_in_band_sync = not env_lib.is_false(
            const.EnvKey.ALLOW_IN_BAND_SYNC,
        )

        self._client = client
        self._http_client = client._http_client
        self._mode = client._mode
        self._api_origin = client.api_origin
        self._fns = {fn.get_id(): fn for fn in functions}
        self._framework = framework

        if streaming is None:
            streaming = env_lib.get_streaming(const.EnvKey.STREAMING)
        self._streaming = streaming or const.Streaming.DISABLE
        if self._streaming == const.Streaming.FORCE:
            self._client.logger.warning("Streaming responses are enabled")

        if thread_pool is None:
            # Only reachable when using Serve (not Connect). For Serve, a thread
            # pool is necessarily required because we can delegate concurrent
            # request handling to the user's HTTP framework.
            #
            # Default to disabled for both async and sync functions, since we
            # expect Connect to automatically handle the config. Or users will
            # explicitly set the config.
            thread_pool = ThreadPoolConfig(
                enable_for_async_fns=False,
                enable_for_sync_fns=False,
                pool=concurrent.futures.ThreadPoolExecutor(),
            )
        self._thread_pool = thread_pool

        signing_key = client.signing_key
        if signing_key is None:
            if self._client.is_production:
                signing_key = os.getenv(const.EnvKey.SIGNING_KEY.value)
                if signing_key is None:
                    self._client.logger.error("missing signing key")
                    raise errors.SigningKeyMissingError()
        self._signing_key = signing_key

        self._signing_key_fallback = client.signing_key_fallback

    @wrap_handler()
    async def post(
        self,
        req: CommRequest,
        request_signing_key: types.MaybeError[str | None],
    ) -> CommResponse | Exception:
        params = parse_query_params(req.query_params)
        if isinstance(params, Exception):
            return params

        if params.probe is server_lib.Probe.TRUST:
            return CommResponse()

        server_kind = transforms.get_server_kind(req.headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None

        middleware = middleware_lib.MiddlewareManager.from_client(
            self._client,
            req.raw_request,
            req.timings,
        )

        request = server_lib.ServerRequest.from_raw(req.body)
        if isinstance(request, Exception):
            return request

        fn_id = params.fn_id
        if fn_id is None:
            return errors.QueryParamMissingError(
                server_lib.QueryParamKey.FUNCTION_ID.value
            )

        # Get the function we should call.
        fn = self._get_function(fn_id)
        if isinstance(fn, Exception):
            return fn

        events = request.events
        steps = request.steps
        if request.use_api:
            # Putting the batch and memoized steps in the request would make it
            # to big, so the Executor is telling the SDK to fetch them from the
            # API

            with req.timings.use_api:
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

        memos = step_lib.StepMemos.from_raw(steps)

        if fn.is_handler_async:
            ctx = execution_lib.Context(
                attempt=request.ctx.attempt,
                event=request.event,
                events=events,
                group=step_lib.Group(),
                logger=self._client.logger,
                run_id=request.ctx.run_id,
                step=step_lib.Step(
                    self._client,
                    execution_lib.ExecutionV0(
                        memos,
                        middleware,
                        request,
                        params.step_id,
                        req.timings,
                    ),
                    middleware,
                    step_lib.StepIDCounter(),
                    params.step_id,
                ),
            )

            if self._thread_pool.enable_for_async_fns:
                # Run async function in a thread pool worker to prevent
                # thread-blocking operations from stalling Inngest functions.
                # Without this, thread-blocking logic in one Inngest function
                # would block all other Inngest functions.
                #
                # Each worker thread creates its own event loop via
                # `asyncio.run()`.

                # This function is runs in a separate thread
                def run_in_thread() -> execution_lib.CallResult:
                    return asyncio.run(
                        fn.call(self._client, ctx, fn_id, middleware)
                    )

                async def run_in_pool() -> execution_lib.CallResult:
                    loop = asyncio.get_running_loop()
                    return await loop.run_in_executor(
                        self._thread_pool.pool,
                        run_in_thread,
                    )

                call_res_task = asyncio.create_task(run_in_pool())
            else:
                # No thread pool: run directly on the main event loop.
                call_res_task = asyncio.create_task(
                    fn.call(self._client, ctx, fn_id, middleware)
                )

            # Streaming sends keepalive bytes while the task runs, then
            # sends the result when complete. Works with both thread pool
            # and direct execution since both produce an asyncio.Task.
            if self._streaming is const.Streaming.FORCE:
                return CommResponse.create_streaming(
                    self._client.logger,
                    call_res_task,
                    self._client.env,
                    self._framework,
                    server_kind,
                    req.timings,
                )

            call_res = await call_res_task
        else:
            # Sync function path.
            ctx_sync = execution_lib.ContextSync(
                attempt=request.ctx.attempt,
                event=request.event,
                events=events,
                group=step_lib.GroupSync(),
                logger=self._client.logger,
                run_id=request.ctx.run_id,
                step=step_lib.StepSync(
                    self._client,
                    execution_lib.ExecutionV0Sync(
                        memos,
                        middleware,
                        request,
                        params.step_id,
                        req.timings,
                    ),
                    middleware,
                    step_lib.StepIDCounter(),
                    params.step_id,
                ),
            )

            fn_call = functools.partial(
                fn.call_sync, self._client, ctx_sync, fn_id, middleware
            )

            if self._thread_pool.enable_for_sync_fns:
                # Run in thread pool to avoid blocking the main event loop.
                loop = asyncio.get_running_loop()
                call_res = await loop.run_in_executor(
                    self._thread_pool.pool,
                    fn_call,
                )
            else:
                # No thread pool: call directly. This blocks the event
                # loop, which is acceptable when CommHandler is used from
                # a sync context (e.g. Flask) where the framework manages
                # threading.
                call_res = fn_call()

        return CommResponse.from_call_result(
            self._client.logger,
            call_res,
            self._client.env,
            self._framework,
            server_kind,
        )

    @wrap_handler_sync()
    def post_sync(
        self,
        req: CommRequest,
        request_signing_key: types.MaybeError[str | None],
    ) -> CommResponse | Exception:
        params = parse_query_params(req.query_params)
        if isinstance(params, Exception):
            return params

        if params.probe is server_lib.Probe.TRUST:
            return CommResponse()

        server_kind = transforms.get_server_kind(req.headers)
        if isinstance(server_kind, Exception):
            self._client.logger.error(server_kind)
            server_kind = None

        middleware = middleware_lib.MiddlewareManager.from_client(
            self._client,
            req.raw_request,
            req.timings,
        )

        request = server_lib.ServerRequest.from_raw(req.body)
        if isinstance(request, Exception):
            return request

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

            with req.timings.use_api:
                fetched_events = self._client._get_batch_sync(
                    request.ctx.run_id
                )
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

        memos = step_lib.StepMemos.from_raw(steps)

        call_res = fn.call_sync(
            self._client,
            execution_lib.ContextSync(
                attempt=request.ctx.attempt,
                event=request.event,
                events=events,
                group=step_lib.GroupSync(),
                logger=self._client.logger,
                run_id=request.ctx.run_id,
                step=step_lib.StepSync(
                    self._client,
                    execution_lib.ExecutionV0Sync(
                        memos,
                        middleware,
                        request,
                        params.step_id,
                        req.timings,
                    ),
                    middleware,
                    step_lib.StepIDCounter(),
                    params.step_id,
                ),
            ),
            params.fn_id,
            middleware,
        )

        return CommResponse.from_call_result(
            self._client.logger,
            call_res,
            self._client.env,
            self._framework,
            server_kind,
        )

    def _get_function(
        self, fn_id: str
    ) -> types.MaybeError[function.Function[typing.Any]]:
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

    @wrap_handler_sync(require_signature=False)
    def get_sync(
        self,
        req: CommRequest,
        request_signing_key: types.MaybeError[str | None],
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

        inspection = _build_inspection_response(
            self,
            req,
            request_signing_key,
        )
        if isinstance(inspection, Exception):
            return inspection

        res_body = inspection.to_dict()
        if isinstance(res_body, Exception):
            return res_body

        return CommResponse(
            body=res_body,
            status_code=200,
        )

    @wrap_handler(require_signature=False)
    async def put(
        self: CommHandler,
        req: CommRequest,
        request_signing_key: types.MaybeError[str | None],
    ) -> CommResponse | Exception:
        """Handle a PUT request."""

        self._client.logger.debug("Syncing app")
        syncer = Syncer(logger=self._client.logger)

        if (
            req.headers.get(server_lib.HeaderKey.SYNC_KIND.value)
            == server_lib.SyncKind.IN_BAND.value
            and self._allow_in_band_sync
        ):
            err: Exception | None = None
            if isinstance(request_signing_key, Exception):
                err = request_signing_key
            elif request_signing_key is None:
                err = Exception("request must be signed for in-band sync")
            if err is not None:
                return CommResponse.from_error(
                    self._client.logger,
                    err,
                    status=http.HTTPStatus.UNAUTHORIZED,
                )
            return syncer.in_band(self, req, request_signing_key)

        return await syncer.out_of_band(self, req)

    @wrap_handler_sync(require_signature=False)
    def put_sync(
        self: CommHandler,
        req: CommRequest,
        request_signing_key: types.MaybeError[str | None],
    ) -> CommResponse | Exception:
        """Handle a PUT request."""

        self._client.logger.debug("Syncing app")
        syncer = Syncer(logger=self._client.logger)

        if (
            req.headers.get(server_lib.HeaderKey.SYNC_KIND.value)
            == server_lib.SyncKind.IN_BAND.value
            and self._allow_in_band_sync
        ):
            err: Exception | None = None
            if isinstance(request_signing_key, Exception):
                err = request_signing_key
            elif request_signing_key is None:
                err = Exception("request must be signed for in-band sync")
            if err is not None:
                return CommResponse.from_error(
                    self._client.logger,
                    err,
                    status=http.HTTPStatus.UNAUTHORIZED,
                )

            return syncer.in_band(self, req, request_signing_key)

        return syncer.out_of_band_sync(self, req)


def _build_inspection_response(
    handler: CommHandler,
    req: CommRequest,
    request_signing_key: types.MaybeError[str | None],
) -> types.MaybeError[
    server_lib.AuthenticatedInspection | server_lib.UnauthenticatedInspection
]:
    server_kind = transforms.get_server_kind(req.headers)
    if isinstance(server_kind, Exception):
        handler._client.logger.error(server_kind)
        server_kind = None

    is_signed = isinstance(request_signing_key, str)
    if is_signed:
        event_key_hash = (
            transforms.hash_event_key(handler._client.event_key)
            if handler._client.event_key
            else None
        )

        signing_key_hash = (
            transforms.hash_signing_key(handler._signing_key)
            if handler._signing_key
            else None
        )

        signing_key_fallback_hash = (
            transforms.hash_signing_key(handler._signing_key_fallback)
            if handler._signing_key_fallback
            else None
        )

        return server_lib.AuthenticatedInspection(
            api_origin=handler._client.api_origin,
            app_id=handler._client.app_id,
            authentication_succeeded=True,
            env=handler._client.env,
            event_api_origin=handler._client.event_api_origin,
            event_key_hash=event_key_hash,
            framework=handler._framework.value,
            function_count=len(handler._fns),
            has_event_key=handler._client.event_key is not None,
            has_signing_key=handler._signing_key is not None,
            has_signing_key_fallback=handler._signing_key_fallback is not None,
            mode=handler._mode,
            serve_origin=req.serve_origin,
            serve_path=req.serve_path,
            signing_key_fallback_hash=signing_key_fallback_hash,
            signing_key_hash=signing_key_hash,
        )

    return server_lib.UnauthenticatedInspection(
        function_count=len(handler._fns),
        has_event_key=handler._client.event_key is not None,
        has_signing_key=handler._signing_key is not None,
        has_signing_key_fallback=handler._signing_key_fallback is not None,
        mode=handler._mode,
    )


class Syncer:
    def __init__(self, logger: types.Logger) -> None:
        self._logger = logger

    def in_band(
        self,
        handler: CommHandler,
        req: CommRequest,
        request_signing_key: types.MaybeError[str | None],
    ) -> types.MaybeError[CommResponse]:
        if not isinstance(request_signing_key, str):
            # This should be checked earlier, but we'll also check it here since
            # it's critical
            return Exception("request must be signed for in-band sync")

        req_body = server_lib.InBandSynchronizeRequest.from_raw(req.body)
        if isinstance(req_body, Exception):
            return req_body

        app_url = net.create_serve_url(
            public_path=req.public_path,
            request_url=req_body.url,
            serve_origin=req.serve_origin,
            serve_path=req.serve_path,
        )

        fn_configs = get_function_configs(app_url, handler._fns)
        if isinstance(fn_configs, Exception):
            return fn_configs

        inspection = _build_inspection_response(
            handler,
            req,
            request_signing_key,
        )
        if isinstance(inspection, Exception):
            return inspection
        if isinstance(inspection, server_lib.UnauthenticatedInspection):
            # Unreachable
            return Exception("request must be signed for in-band sync")

        res_body = server_lib.InBandSynchronizeResponse(
            app_id=handler._client.app_id,
            env=handler._client.env,
            framework=handler._framework,
            functions=fn_configs,
            inspection=inspection,
            platform=None,
            url=app_url,
        ).to_dict()
        if isinstance(res_body, Exception):
            return res_body

        # Remove any None values from the response body. If we don't Go
        # marshalling may break in the Inngest server. Specifically, we saw this
        # with the concurrency scope.
        res_body = transforms.deep_strip_none(res_body)

        self._logger.debug("Responding to in-band sync")

        return CommResponse(
            body=res_body,
            headers={
                server_lib.HeaderKey.SYNC_KIND.value: server_lib.SyncKind.IN_BAND.value,
            },
        )

    def _create_out_of_band_request(
        self,
        handler: CommHandler,
        req: CommRequest,
    ) -> types.MaybeError[CommResponse | httpx.Request]:
        app_url = net.create_serve_url(
            public_path=req.public_path,
            request_url=req.request_url,
            serve_origin=req.serve_origin,
            serve_path=req.serve_path,
        )

        server_kind = transforms.get_server_kind(req.headers)
        if isinstance(server_kind, Exception):
            handler._client.logger.error(server_kind)
            server_kind = None

        if server_kind is not None and server_kind != handler._mode:
            msg: str
            if server_kind == server_lib.ServerKind.DEV_SERVER:
                msg = "Sync rejected since it's from a Dev Server but expected Cloud"
            else:
                msg = "Sync rejected since it's from Cloud but expected Dev Server"

            handler._client.logger.error(msg)
            return CommResponse.from_error_code(
                server_lib.ErrorCode.SERVER_KIND_MISMATCH,
                msg,
                http.HTTPStatus.BAD_REQUEST,
            )

        params = parse_query_params(req.query_params)
        if isinstance(params, Exception):
            return params

        registration_url = urllib.parse.urljoin(
            handler._api_origin,
            "/fn/register",
        )

        fn_configs = get_function_configs(app_url, handler._fns)
        if isinstance(fn_configs, Exception):
            return fn_configs

        body = server_lib.SynchronizeRequest(
            app_name=handler._client.app_id,
            deploy_type=server_lib.DeployType.PING,
            framework=handler._framework,
            functions=fn_configs,
            sdk=f"{const.LANGUAGE}:v{const.VERSION}",
            url=app_url,
            v="0.1",
        ).to_dict()
        if isinstance(body, Exception):
            return body

        headers = net.create_headers(
            env=handler._client.env,
            framework=handler._framework,
            server_kind=server_kind,
        )

        outgoing_params = {}
        if params.sync_id is not None:
            outgoing_params[server_lib.QueryParamKey.SYNC_ID.value] = (
                params.sync_id
            )

        # Remove any None values from the response body. If we don't Go
        # marshalling may break in the Inngest server. Specifically, we saw this
        # with the concurrency scope.
        body = transforms.deep_strip_none(body)

        return handler._http_client.build_httpx_request(
            "POST",
            registration_url,
            headers=headers,
            json=body,
            params=outgoing_params,
            timeout=30,
        )

    def _parse_out_of_band_response(
        self,
        handler: CommHandler,
        res: httpx.Response,
    ) -> types.MaybeError[CommResponse]:
        try:
            server_res_body = res.json()
        except Exception:
            return errors.RegistrationFailedError("response is not valid JSON")

        if not isinstance(server_res_body, dict):
            return errors.RegistrationFailedError("response is not an object")

        if res.status_code >= 400:
            msg = server_res_body.get("error")
            if not isinstance(msg, str):
                msg = "registration failed"
            comm_res = CommResponse.from_error(
                handler._client.logger,
                errors.RegistrationFailedError(msg.strip()),
            )
            comm_res.status_code = res.status_code

        return CommResponse(
            body=server_res_body,
            headers={
                server_lib.HeaderKey.SYNC_KIND.value: server_lib.SyncKind.OUT_OF_BAND.value,
            },
        )

    async def out_of_band(
        self,
        handler: CommHandler,
        req: CommRequest,
    ) -> types.MaybeError[CommResponse]:
        prep = self._create_out_of_band_request(handler, req)
        if isinstance(prep, Exception):
            return prep
        if isinstance(prep, CommResponse):
            return prep

        self._logger.debug(f"Sending out-of-band sync request to {prep.url}")

        res = await net.fetch_with_auth_fallback(
            handler._http_client._http_client,
            handler._http_client._http_client_sync,
            prep,
            signing_key=handler._signing_key,
            signing_key_fallback=handler._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        return self._parse_out_of_band_response(handler, res)

    def out_of_band_sync(
        self,
        handler: CommHandler,
        req: CommRequest,
    ) -> types.MaybeError[CommResponse]:
        prep = self._create_out_of_band_request(handler, req)
        if isinstance(prep, Exception):
            return prep
        if isinstance(prep, CommResponse):
            return prep

        self._logger.debug(f"Sending out-of-band sync request to {prep.url}")

        res = net.fetch_with_auth_fallback_sync(
            handler._http_client._http_client_sync,
            prep,
            signing_key=handler._signing_key,
            signing_key_fallback=handler._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        return self._parse_out_of_band_response(handler, res)


def get_function_configs(
    app_url: str,
    fns: dict[str, function.Function[typing.Any]],
) -> types.MaybeError[list[server_lib.FunctionConfig]]:
    configs: list[server_lib.FunctionConfig] = []
    for fn in fns.values():
        config = fn.get_config(app_url)
        configs.append(config.main)

        if config.on_failure is not None:
            configs.append(config.on_failure)

    if len(configs) == 0:
        return errors.FunctionConfigInvalidError("no functions found")
    return configs
