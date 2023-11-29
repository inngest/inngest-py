from __future__ import annotations

import logging
import os
import time
import typing
import urllib.parse

import httpx

from . import const, env, errors, event_lib, net, types

if typing.TYPE_CHECKING:
    from . import middleware_lib


class Inngest:
    middleware: list[
        type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
    ]

    def __init__(
        self,
        *,
        app_id: str,
        event_api_base_url: str | None = None,
        event_key: str | None = None,
        is_production: bool | None = None,
        logger: types.Logger | None = None,
        middleware: list[
            type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
        ]
        | None = None,
    ) -> None:
        """
        Args:
        ----
            app_id: Unique Inngest ID. Changing this ID will make Inngest think
                it's a different app.
            event_api_base_url: Origin for the Inngest Event API.
            event_key: Inngest event key.
            is_production: Whether the app is in production.
            logger: Logger to use.
            middleware: List of middleware to use.
        """

        self.app_id = app_id

        self.is_production = (
            is_production if is_production is not None else env.is_prod()
        )

        self.logger = logger or logging.getLogger(__name__)
        self.middleware = middleware or []

        if event_key is None:
            if not self.is_production:
                event_key = "NO_EVENT_KEY_SET"
            else:
                event_key = os.getenv(const.EnvKey.EVENT_KEY.value)
        if event_key is None:
            self.logger.error("missing event key")
            raise errors.MissingEventKeyError()
        self._event_key = event_key

        event_origin = event_api_base_url
        if event_origin is None:
            if not self.is_production:
                self.logger.info("Defaulting event origin to Dev Server")
                event_origin = const.DEV_SERVER_ORIGIN
            else:
                event_origin = const.DEFAULT_EVENT_ORIGIN
        self._event_api_origin = event_origin

    def _build_send_request(
        self,
        events: list[event_lib.Event],
    ) -> types.MaybeError[httpx.Request]:
        url = urllib.parse.urljoin(
            self._event_api_origin, f"/e/{self._event_key}"
        )

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
