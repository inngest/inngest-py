from __future__ import annotations

import logging
import os
import time
import typing
import urllib.parse

import httpx

from . import (
    const,
    env_lib,
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
        type[
            typing.Union[
                middleware_lib.Middleware, middleware_lib.MiddlewareSync
            ]
        ]
    ]

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
            list[
                type[
                    typing.Union[
                        middleware_lib.Middleware, middleware_lib.MiddlewareSync
                    ]
                ]
            ]
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
        self.is_production = self._mode == const.ServerKind.CLOUD

        self.middleware = middleware or []
        self._event_key = event_key or os.getenv(const.EnvKey.EVENT_KEY.value)

        self._signing_key = signing_key or os.getenv(
            const.EnvKey.SIGNING_KEY.value
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

        api_origin = api_base_url or os.getenv(const.EnvKey.API_BASE_URL.value)
        if api_origin is None:
            if self._mode == const.ServerKind.DEV_SERVER:
                api_origin = const.DEV_SERVER_ORIGIN
            else:
                api_origin = const.DEFAULT_API_ORIGIN
        self._api_origin = api_origin

        event_origin = event_api_base_url or os.getenv(
            const.EnvKey.EVENT_API_BASE_URL.value
        )
        if event_origin is None:
            if self._mode == const.ServerKind.DEV_SERVER:
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
            if self._mode == const.ServerKind.DEV_SERVER:
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
            signing_key=None,
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
            typing.Union[
                middleware_lib.Middleware, middleware_lib.MiddlewareSync
            ]
        ],
    ) -> None:
        self.middleware = [*self.middleware, middleware]

    def create_function(
        self,
        *,
        batch_events: typing.Optional[function_config.Batch] = None,
        cancel: typing.Optional[list[function_config.Cancel]] = None,
        concurrency: typing.Optional[list[function_config.Concurrency]] = None,
        debounce: typing.Optional[function_config.Debounce] = None,
        fn_id: str,
        middleware: typing.Optional[
            list[
                type[
                    typing.Union[
                        middleware_lib.Middleware, middleware_lib.MiddlewareSync
                    ]
                ]
            ]
        ] = None,
        name: typing.Optional[str] = None,
        on_failure: typing.Union[
            function.FunctionHandlerAsync, function.FunctionHandlerSync, None
        ] = None,
        rate_limit: typing.Optional[function_config.RateLimit] = None,
        retries: typing.Optional[int] = None,
        throttle: typing.Optional[function_config.Throttle] = None,
        trigger: typing.Union[
            function_config.TriggerCron,
            function_config.TriggerEvent,
            list[
                typing.Union[
                    function_config.TriggerCron, function_config.TriggerEvent
                ]
            ],
        ],
    ) -> typing.Callable[
        [
            typing.Union[
                function.FunctionHandlerAsync, function.FunctionHandlerSync
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
            func: typing.Union[
                function.FunctionHandlerAsync, function.FunctionHandlerSync
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
                    local_id=fn_id,
                    name=name or fn_id,
                    on_failure=on_failure,
                    rate_limit=rate_limit,
                    retries=retries,
                    throttle=throttle,
                ),
                triggers,
                func,
                middleware,
            )

        return decorator

    async def _get(self, url: str) -> httpx.Response:
        """
        Perform an asynchronous HTTP GET request. Handles authn
        """

        async with httpx.AsyncClient() as client:
            return await client.get(
                url,
                headers=net.create_headers(
                    env=self._env,
                    framework=None,
                    server_kind=None,
                    signing_key=self._signing_key,
                ),
            )

    def _get_sync(self, url: str) -> httpx.Response:
        """
        Perform a synchronous HTTP GET request. Handles authn
        """

        return httpx.get(
            url,
            headers=net.create_headers(
                env=self._env,
                framework=None,
                server_kind=None,
                signing_key=self._signing_key,
            ),
        )

    async def _get_batch(self, run_id: str) -> list[event_lib.Event]:
        """
        Fetch a batch of events from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/batch",
        )
        data = (await self._get(url)).json()
        if not isinstance(data, list):
            raise errors.BodyInvalidError("batch data is not an array")

        events = []
        for e in data:
            events.append(event_lib.Event.model_validate(e))
        return events

    def _get_batch_sync(self, run_id: str) -> list[event_lib.Event]:
        """
        Fetch a batch of events from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/batch",
        )
        data = self._get_sync(url).json()
        if not isinstance(data, list):
            raise errors.BodyInvalidError("batch data is not an array")

        events = []
        for e in data:
            events.append(event_lib.Event.model_validate(e))
        return events

    async def _get_steps(self, run_id: str) -> dict[str, object]:
        """
        Fetch memoized step data from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/actions",
        )
        data = (await self._get(url)).json()
        if not isinstance(data, dict):
            raise errors.BodyInvalidError("step data is not an object")

        return data

    def _get_steps_sync(self, run_id: str) -> dict[str, object]:
        """
        Fetch memoized step data from the API
        """

        url = urllib.parse.urljoin(
            self._api_origin,
            f"/v0/runs/{run_id}/actions",
        )
        data = self._get_sync(url).json()
        if not isinstance(data, dict):
            raise errors.BodyInvalidError("step data is not an object")

        return data

    async def send(
        self,
        events: typing.Union[event_lib.Event, list[event_lib.Event]],
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
        events: typing.Union[event_lib.Event, list[event_lib.Event]],
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
        raise errors.BodyInvalidError("unexpected response when sending events")

    ids = body["ids"]
    if not isinstance(ids, list):
        raise errors.BodyInvalidError("unexpected response when sending events")

    return ids


def _get_mode(
    logger: types.Logger,
    is_production: typing.Optional[bool],
) -> const.ServerKind:
    if is_production is not None:
        if is_production:
            logger.debug("Cloud mode enabled by client argument")
            return const.ServerKind.CLOUD

        logger.debug("Dev Server mode enabled by client argument")
        return const.ServerKind.DEV_SERVER

    if env_lib.is_true(const.EnvKey.DEV):
        logger.debug(
            f"Dev Server mode enabled by {const.EnvKey.DEV.value} env var"
        )
        return const.ServerKind.DEV_SERVER

    logger.debug(
        f"Cloud mode enabled. Set {const.EnvKey.DEV.value} to enable development mode"
    )
    return const.ServerKind.CLOUD
