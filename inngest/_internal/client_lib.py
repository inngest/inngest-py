from __future__ import annotations

import logging
import os
import time
import typing
import urllib.parse

import httpx

from . import (
    const,
    env,
    errors,
    event_lib,
    function,
    function_config,
    net,
    types,
)

if typing.TYPE_CHECKING:
    from . import middleware_lib


# Dummy value
_DEV_SERVER_EVENT_KEY = "NO_EVENT_KEY_SET"


class Inngest:
    middleware: list[
        type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
    ]

    @property
    def api_origin(self) -> str:
        return self._api_origin

    @property
    def event_api_origin(self) -> str:
        return self._event_api_origin

    @property
    def event_key(self) -> str | None:
        return self._event_key

    @property
    def signing_key(self) -> str | None:
        return self._signing_key

    def __init__(
        self,
        *,
        api_base_url: str | None = None,
        app_id: str,
        event_api_base_url: str | None = None,
        event_key: str | None = None,
        is_production: bool | None = None,
        logger: types.Logger | None = None,
        middleware: list[
            type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
        ]
        | None = None,
        signing_key: str | None = None,
    ) -> None:
        """
        Args:
        ----
            api_base_url: Origin for the Inngest REST API.
            app_id: Unique Inngest ID. Changing this ID will make Inngest think
                it's a different app.
            event_api_base_url: Origin for the Inngest Event API.
            event_key: Inngest event key.
            is_production: Whether the app is in production. This affects
                request signature verification and default Inngest server URLs.
            logger: Logger to use.
            middleware: List of middleware to use.
            signing_key: Inngest signing key.
        """

        self.app_id = app_id

        if is_production is None:
            is_production = env.is_truthy(
                const.EnvKey.DEV,
                # Default to prod for security reasons
                default=True,
            )
        self.is_production = is_production

        self.logger = logger or logging.getLogger(__name__)
        self.middleware = middleware or []
        self._event_key = event_key or os.getenv(const.EnvKey.EVENT_KEY.value)

        self._signing_key = signing_key or os.getenv(
            const.EnvKey.SIGNING_KEY.value
        )
        if self._signing_key is None and self.is_production:
            raise errors.MissingSigningKeyError()

        api_origin = api_base_url or os.getenv(const.EnvKey.API_BASE_URL.value)
        if api_origin is None:
            if not self.is_production:
                api_origin = const.DEV_SERVER_ORIGIN
            else:
                api_origin = const.DEFAULT_API_ORIGIN
        self._api_origin = api_origin

        event_origin = event_api_base_url or os.getenv(
            const.EnvKey.EVENT_API_BASE_URL.value
        )
        if event_origin is None:
            if not self.is_production:
                event_origin = const.DEV_SERVER_ORIGIN
            else:
                event_origin = const.DEFAULT_EVENT_ORIGIN
        self._event_api_origin = event_origin

    def _build_send_request(
        self,
        events: list[event_lib.Event],
    ) -> types.MaybeError[httpx.Request]:
        event_key: str
        if self._event_key is not None:
            event_key = self._event_key
        else:
            if not self.is_production:
                event_key = _DEV_SERVER_EVENT_KEY
            else:
                return errors.MissingEventKeyError()

        url = urllib.parse.urljoin(self._event_api_origin, f"/e/{event_key}")

        # The client is irrespective of framework.
        framework = None

        # It'd be nice to know the expected server kind, but it's unclear how to
        # do that.
        server_kind = None

        headers = net.create_headers(framework, server_kind)

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

        return httpx.Client().build_request(
            "POST",
            url,
            headers=headers,
            json=body,
            timeout=30,
        )

    def add_middleware(
        self,
        middleware: type[
            middleware_lib.Middleware | middleware_lib.MiddlewareSync
        ],
    ) -> None:
        self.middleware = [*self.middleware, middleware]

    def create_function(
        self,
        *,
        batch_events: function_config.Batch | None = None,
        cancel: list[function_config.Cancel] | None = None,
        debounce: function_config.Debounce | None = None,
        fn_id: str,
        middleware: list[
            type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
        ]
        | None = None,
        name: str | None = None,
        on_failure: function.FunctionHandlerAsync
        | function.FunctionHandlerSync
        | None = None,
        rate_limit: function_config.RateLimit | None = None,
        retries: int | None = None,
        throttle: function_config.Throttle | None = None,
        trigger: function_config.TriggerCron | function_config.TriggerEvent,
    ) -> typing.Callable[
        [function.FunctionHandlerAsync | function.FunctionHandlerSync],
        function.Function,
    ]:
        """
        Create an Inngest function.

        Args:
        ----
            batch_events: Event batching config.
            cancel: Run cancellation config.
            debounce: Debouncing config.
            fn_id: Function ID. Changing this ID will make Inngest think this is a
                new function.
            middleware: Middleware to apply to this function.
            name: Human-readable function name. (Defaults to the function ID).
            on_failure: Function to call when this function fails.
            rate_limit: Rate limiting config.
            retries: Number of times to retry this function.
            throttle: Throttling config.
            trigger: What should trigger runs of this function.
        """

        fully_qualified_fn_id = f"{self.app_id}-{fn_id}"

        def decorator(
            func: function.FunctionHandlerAsync | function.FunctionHandlerSync
        ) -> function.Function:
            return function.Function(
                function.FunctionOpts(
                    batch_events=batch_events,
                    cancel=cancel,
                    debounce=debounce,
                    id=fully_qualified_fn_id,
                    name=name or fn_id,
                    on_failure=on_failure,
                    rate_limit=rate_limit,
                    retries=retries,
                    throttle=throttle,
                ),
                trigger,
                func,
                middleware,
            )

        return decorator

    async def send(
        self,
        events: event_lib.Event | list[event_lib.Event],
    ) -> list[str]:
        """
        Send one or more events. This method is asynchronous.

        Args:
        ----
            events: An event or list of events to send.
        """

        if not isinstance(events, list):
            events = [events]

        async with httpx.AsyncClient() as client:
            req = self._build_send_request(events)
            if isinstance(req, Exception):
                raise req
            return _extract_ids((await client.send(req)).json())

    def send_sync(
        self,
        events: event_lib.Event | list[event_lib.Event],
    ) -> list[str]:
        """
        Send one or more events. This method is synchronous.

        Args:
        ----
            events: An event or list of events to send.
        """

        if not isinstance(events, list):
            events = [events]

        with httpx.Client() as client:
            req = self._build_send_request(events)
            if isinstance(req, Exception):
                raise req
            return _extract_ids((client.send(req)).json())

    def set_logger(self, logger: types.Logger) -> None:
        self.logger = logger


def _extract_ids(body: object) -> list[str]:
    if not isinstance(body, dict) or "ids" not in body:
        raise errors.InvalidBodyError("unexpected response when sending events")

    ids = body["ids"]
    if not isinstance(ids, list):
        raise errors.InvalidBodyError("unexpected response when sending events")

    return ids
