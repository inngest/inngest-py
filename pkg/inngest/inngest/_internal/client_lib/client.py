from __future__ import annotations

import logging
import os
import time
import typing
import urllib.parse

import httpx
import pydantic

from inngest._internal import (
    const,
    env_lib,
    errors,
    function,
    middleware_lib,
    net,
    server_lib,
    types,
)

from . import models
from .utils import get_api_origin, get_event_api_origin

if typing.TYPE_CHECKING:
    from inngest._internal import execution_lib

# Dummy value
_DEV_SERVER_EVENT_KEY = "NO_EVENT_KEY_SET"


class Inngest:
    middleware: list[middleware_lib.UninitializedMiddleware]

    @property
    def api_origin(self) -> str:
        return self._api_origin

    @property
    def env(self) -> typing.Optional[str]:
        return self._env

    @property
    def event_api_origin(self) -> str:
        return self._event_api_origin

    @property
    def event_key(self) -> typing.Optional[str]:
        return self._event_key

    @property
    def signing_key(self) -> typing.Optional[str]:
        return self._signing_key

    @property
    def signing_key_fallback(self) -> typing.Optional[str]:
        return self._signing_key_fallback

    def __init__(
        self,
        *,
        api_base_url: typing.Optional[str] = None,
        app_id: str,
        env: typing.Optional[str] = None,
        event_api_base_url: typing.Optional[str] = None,
        event_key: typing.Optional[str] = None,
        is_production: typing.Optional[bool] = None,
        logger: typing.Optional[types.Logger] = None,
        middleware: typing.Optional[
            list[middleware_lib.UninitializedMiddleware]
        ] = None,
        signing_key: typing.Optional[str] = None,
    ) -> None:
        """
        Args:
        ----
            api_base_url: Origin for the Inngest REST API.
            app_id: Unique Inngest ID. Changing this ID will make Inngest think
                it's a different app.
            env: Branch environment to use. This is only necessary for branch
                environments.
            event_api_base_url: Origin for the Inngest Event API.
            event_key: Inngest event key.
            is_production: Whether the app is in production. This affects
                request signature verification and default Inngest server URLs.
            logger: Logger to use.
            middleware: List of middleware to use.
            signing_key: Inngest signing key.
        """

        self.app_id = app_id
        self.logger = logger or logging.getLogger(__name__)
        self._mode = _get_mode(self.logger, is_production)

        # TODO: Delete this during next major version bump
        self.is_production = self._mode == server_lib.ServerKind.CLOUD

        self.middleware = middleware or []
        self._event_key = event_key or os.getenv(const.EnvKey.EVENT_KEY.value)

        self._signing_key = signing_key or os.getenv(
            const.EnvKey.SIGNING_KEY.value
        )

        self._signing_key_fallback = os.getenv(
            const.EnvKey.SIGNING_KEY_FALLBACK.value
        )

        self._env = env or env_lib.get_environment_name()
        if (
            self._env is None
            and self._signing_key is not None
            and "branch" in self._signing_key
        ):
            self.logger.warning(
                "Signing key is for a branch environment but no branch environment is specified. This may cause unexpected behavior"
            )

        maybe_str = get_api_origin(api_base_url, self._mode)
        if isinstance(maybe_str, Exception):
            raise maybe_str
        self._api_origin = maybe_str

        maybe_str = get_event_api_origin(event_api_base_url, self._mode)
        if isinstance(maybe_str, Exception):
            raise maybe_str
        self._event_api_origin = maybe_str

        self._http_client = net.ThreadAwareAsyncHTTPClient().initialize()
        self._http_client_sync = httpx.Client()

    def _build_send_request(
        self,
        events: list[server_lib.Event],
    ) -> types.MaybeError[httpx.Request]:
        event_key: str
        if self._event_key is not None:
            event_key = self._event_key
        else:
            if self._mode == server_lib.ServerKind.DEV_SERVER:
                event_key = _DEV_SERVER_EVENT_KEY
            else:
                return errors.EventKeyUnspecifiedError()

        url = urllib.parse.urljoin(self._event_api_origin, f"/e/{event_key}")

        # The client is irrespective of framework.
        framework = None

        # It'd be nice to know the expected server kind, but it's unclear how to
        # do that.
        server_kind = None

        headers = net.create_headers(
            env=self._env,
            framework=framework,
            server_kind=server_kind,
        )

        body = []
        for event in events:
            d = event.to_dict()
            if isinstance(d, Exception):
                return d

            if d.get("id") == "":
                del d["id"]
            if d.get("ts") == 0:
                d["ts"] = int(time.time() * 1000)
            body.append(d)

        return self._http_client_sync.build_request(
            "POST",
            url,
            headers=headers,
            json=body,
            timeout=30,
        )

    def add_middleware(
        self,
        middleware: middleware_lib.UninitializedMiddleware,
    ) -> None:
        self.middleware = [*self.middleware, middleware]

    def create_function(
        self,
        *,
        batch_events: typing.Optional[server_lib.Batch] = None,
        cancel: typing.Optional[list[server_lib.Cancel]] = None,
        concurrency: typing.Optional[list[server_lib.Concurrency]] = None,
        debounce: typing.Optional[server_lib.Debounce] = None,
        fn_id: str,
        idempotency: typing.Optional[str] = None,
        middleware: typing.Optional[
            list[middleware_lib.UninitializedMiddleware]
        ] = None,
        name: typing.Optional[str] = None,
        on_failure: typing.Union[
            execution_lib.FunctionHandlerAsync,
            execution_lib.FunctionHandlerSync,
            None,
        ] = None,
        priority: typing.Optional[server_lib.Priority] = None,
        rate_limit: typing.Optional[server_lib.RateLimit] = None,
        retries: typing.Optional[int] = None,
        throttle: typing.Optional[server_lib.Throttle] = None,
        trigger: typing.Union[
            server_lib.TriggerCron,
            server_lib.TriggerEvent,
            list[typing.Union[server_lib.TriggerCron, server_lib.TriggerEvent]],
        ],
        type_adapter: type[pydantic.BaseModel]
        | pydantic.TypeAdapter[typing.Any]
        | None = None,
    ) -> typing.Callable[
        [
            typing.Union[
                execution_lib.FunctionHandlerAsync,
                execution_lib.FunctionHandlerSync,
            ]
        ],
        function.Function,
    ]:
        """
        Create an Inngest function.

        Args:
        ----
            batch_events: Event batching config.
            cancel: Run cancellation config.
            concurrency: Concurrency config.
            debounce: Debouncing config.
            fn_id: Function ID. Changing this ID will make Inngest think this is a new function.
            idempotency: A key expression which is used to prevent duplicate events from triggering a function over 24 hours.
            middleware: Middleware to apply to this function.
            name: Human-readable function name. (Defaults to the function ID).
            on_failure: Function to call when this function fails.
            priority: Prioritize function runs.
            rate_limit: Rate limiting config.
            retries: Number of times to retry this function.
            throttle: Throttling config.
            trigger: What should trigger runs of this function.
            type_adapter: Adapter for Pydantic output deserialization.
        """

        fully_qualified_fn_id = f"{self.app_id}-{fn_id}"

        def decorator(
            func: typing.Union[
                execution_lib.FunctionHandlerAsync,
                execution_lib.FunctionHandlerSync,
            ],
        ) -> function.Function:
            triggers = trigger if isinstance(trigger, list) else [trigger]
            return function.Function(
                function.FunctionOpts(
                    batch_events=batch_events,
                    cancel=cancel,
                    concurrency=concurrency,
                    debounce=debounce,
                    fully_qualified_id=fully_qualified_fn_id,
                    idempotency=idempotency,
                    local_id=fn_id,
                    name=name or fn_id,
                    on_failure=on_failure,
                    priority=priority,
                    rate_limit=rate_limit,
                    retries=retries,
                    throttle=throttle,
                ),
                triggers,
                func,
                type_adapter,
                middleware,
            )

        return decorator

    async def _get(self, url: str) -> types.MaybeError[httpx.Response]:
        """
        Perform an asynchronous HTTP GET request. Handles authn
        """

        req = self._http_client_sync.build_request(
            "GET",
            url,
            headers=net.create_headers(
                env=self._env,
                framework=None,
                server_kind=None,
            ),
        )

        res = await net.fetch_with_auth_fallback(
            self._http_client,
            self._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        if res.status_code >= 400:
            return Exception(f"HTTP error: {res.status_code} {res.text}")

        return res

    def _get_sync(self, url: str) -> types.MaybeError[httpx.Response]:
        """
        Perform a synchronous HTTP GET request. Handles authn
        """

        req = self._http_client_sync.build_request(
            "GET",
            url,
            headers=net.create_headers(
                env=self._env,
                framework=None,
                server_kind=None,
            ),
        )

        res = net.fetch_with_auth_fallback_sync(
            self._http_client_sync,
            req,
            signing_key=self._signing_key,
            signing_key_fallback=self._signing_key_fallback,
        )
        if isinstance(res, Exception):
            return res

        if res.status_code >= 400:
            return Exception(f"HTTP error: {res.status_code} {res.text}")

        return res

    async def _get_batch(
        self, run_id: str
    ) -> types.MaybeError[list[server_lib.Event]]:
        """
        Fetch a batch of events from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/batch",
        )
        res = await self._get(url)
        if isinstance(res, Exception):
            return res

        data = res.json()
        if not isinstance(data, list):
            raise errors.BodyInvalidError("batch data is not an array")

        events = []
        for e in data:
            events.append(server_lib.Event.model_validate(e))
        return events

    def _get_batch_sync(
        self, run_id: str
    ) -> types.MaybeError[list[server_lib.Event]]:
        """
        Fetch a batch of events from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/batch",
        )
        res = self._get_sync(url)
        if isinstance(res, Exception):
            return res

        data = res.json()
        if not isinstance(data, list):
            raise errors.BodyInvalidError("batch data is not an array")

        events = []
        for e in data:
            events.append(server_lib.Event.model_validate(e))
        return events

    async def _get_steps(
        self, run_id: str
    ) -> types.MaybeError[dict[str, object]]:
        """
        Fetch memoized step data from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/actions",
        )
        res = await self._get(url)
        if isinstance(res, Exception):
            return res

        data = res.json()
        if not isinstance(data, dict):
            raise errors.BodyInvalidError("step data is not an object")

        return data

    def _get_steps_sync(
        self, run_id: str
    ) -> types.MaybeError[dict[str, object]]:
        """
        Fetch memoized step data from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/actions",
        )
        res = self._get_sync(url)
        if isinstance(res, Exception):
            return res

        data = res.json()
        if not isinstance(data, dict):
            raise errors.BodyInvalidError("step data is not an object")

        return data

    async def send(
        self,
        events: typing.Union[server_lib.Event, list[server_lib.Event]],
        *,
        skip_middleware: bool = False,
    ) -> list[str]:
        """
        Send one or more events. This method is asynchronous.

        Args:
        ----
            events: An event or list of events to send.
            skip_middleware: Whether to skip middleware.
        """

        if not isinstance(events, list):
            events = [events]

        middleware = None
        if not skip_middleware:
            middleware = middleware_lib.MiddlewareManager.from_client(
                self,
                raw_request=None,
            )
            await middleware.before_send_events(events)

        req = self._build_send_request(events)
        if isinstance(req, Exception):
            raise req

        result = models.SendEventsResult.from_raw(
            (
                await net.fetch_with_thready_safety(
                    self._http_client,
                    self._http_client_sync,
                    req,
                )
            ).json()
        )
        if isinstance(result, Exception):
            raise result

        if middleware is not None:
            err = await middleware.after_send_events(result)
            if isinstance(err, Exception):
                raise err

        if result.error is not None:
            raise errors.SendEventsError(result.error, result.ids)

        return result.ids

    def send_sync(
        self,
        events: typing.Union[server_lib.Event, list[server_lib.Event]],
        *,
        skip_middleware: bool = False,
    ) -> list[str]:
        """
        Send one or more events. This method is synchronous.

        Args:
        ----
            events: An event or list of events to send.
            skip_middleware: Whether to skip middleware.
        """

        if not isinstance(events, list):
            events = [events]

        middleware = None
        if not skip_middleware:
            middleware = middleware_lib.MiddlewareManager.from_client(
                self,
                raw_request=None,
            )
            err = middleware.before_send_events_sync(events)
            if isinstance(err, Exception):
                raise err

        req = self._build_send_request(events)
        if isinstance(req, Exception):
            raise req

        result = models.SendEventsResult.from_raw(
            (self._http_client_sync.send(req)).json(),
        )
        if isinstance(result, Exception):
            raise result

        if middleware is not None:
            err = middleware.after_send_events_sync(result)
            if isinstance(err, Exception):
                raise err

        if result.error is not None:
            raise errors.SendEventsError(result.error, result.ids)

        return result.ids

    def set_logger(self, logger: types.Logger) -> None:
        self.logger = logger


def _get_mode(
    logger: types.Logger,
    is_production: typing.Optional[bool],
) -> server_lib.ServerKind:
    if is_production is not None:
        if is_production:
            logger.debug("Cloud mode enabled by client argument")
            return server_lib.ServerKind.CLOUD

        logger.debug("Dev Server mode enabled by client argument")
        return server_lib.ServerKind.DEV_SERVER

    if env_lib.is_truthy(const.EnvKey.DEV):
        logger.debug(
            f"Dev Server mode enabled by {const.EnvKey.DEV.value} env var"
        )
        return server_lib.ServerKind.DEV_SERVER

    logger.debug(
        f"Cloud mode enabled. Set {const.EnvKey.DEV.value} to enable development mode"
    )
    return server_lib.ServerKind.CLOUD
