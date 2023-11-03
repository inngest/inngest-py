from __future__ import annotations

import logging
import os
import time
import typing
import urllib.parse

import httpx

from . import const, env, errors, event_lib, net, result, types

if typing.TYPE_CHECKING:
    from . import middleware_lib


class Inngest:
    middleware: list[
        typing.Type[middleware_lib.Middleware | middleware_lib.MiddlewareSync]
    ]

    def __init__(
        self,
        *,
        app_id: str,
        base_url: str | None = None,
        event_key: str | None = None,
        is_production: bool | None = None,
        logger: types.Logger | None = None,
        middleware: list[
            typing.Type[
                middleware_lib.Middleware | middleware_lib.MiddlewareSync
            ]
        ]
        | None = None,
    ) -> None:
        self.app_id = app_id
        self.base_url = base_url
        self.is_production = is_production or env.is_prod()
        self.logger = logger or logging.getLogger(__name__)
        self.middleware = middleware or []

        if event_key is None:
            if not self.is_production:
                event_key = "NO_EVENT_KEY_SET"
            else:
                event_key = os.getenv(const.EnvKey.EVENT_KEY.value)
        if event_key is None:
            self.logger.error("missing event key")
            raise errors.MissingEventKey()
        self._event_key = event_key

        event_origin = base_url
        if event_origin is None:
            if not self.is_production:
                self.logger.info("Defaulting event origin to Dev Server")
                event_origin = const.DEV_SERVER_ORIGIN
            else:
                event_origin = const.DEFAULT_EVENT_ORIGIN
        self._event_origin = event_origin

    def _build_send_request(
        self,
        events: list[event_lib.Event],
    ) -> result.Result[httpx.Request, Exception]:
        url = urllib.parse.urljoin(self._event_origin, f"/e/{self._event_key}")
        headers = net.create_headers()

        body = []
        for event in events:
            match event.to_dict():
                case result.Ok(d):
                    pass
                case result.Err(err):
                    return result.Err(err)

            if d.get("id") == "":
                del d["id"]
            if d.get("ts") == 0:
                d["ts"] = int(time.time() * 1000)
            body.append(d)

        return result.Ok(
            httpx.Client().build_request(
                "POST",
                url,
                headers=headers,
                json=body,
                timeout=30,
            )
        )

    def add_middleware(
        self,
        middleware: typing.Type[
            middleware_lib.Middleware | middleware_lib.MiddlewareSync
        ],
    ) -> None:
        self.middleware = [*self.middleware, middleware]

    async def send(
        self,
        events: event_lib.Event | list[event_lib.Event],
    ) -> list[str]:
        if not isinstance(events, list):
            events = [events]

        async with httpx.AsyncClient() as client:
            match self._build_send_request(events):
                case result.Ok(req):
                    ids = _extract_ids((await client.send(req)).json())
                case result.Err(err):
                    raise err
        return ids

    def send_sync(
        self,
        events: event_lib.Event | list[event_lib.Event],
    ) -> list[str]:
        if not isinstance(events, list):
            events = [events]

        with httpx.Client() as client:
            match self._build_send_request(events):
                case result.Ok(req):
                    ids = _extract_ids(client.send(req).json())
                case result.Err(err):
                    raise err
        return ids

    def set_logger(self, logger: types.Logger) -> None:
        self.logger = logger


def _extract_ids(body: object) -> list[str]:
    if not isinstance(body, dict) or "ids" not in body:
        raise errors.InvalidBody("unexpected response when sending events")

    ids = body["ids"]
    if not isinstance(ids, list):
        raise errors.InvalidBody("unexpected response when sending events")

    return ids
