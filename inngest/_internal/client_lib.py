from __future__ import annotations

import logging
import os
import time
import urllib.parse

from . import const, env, errors, event_lib, net


class Inngest:
    def __init__(
        self,
        *,
        app_id: str,
        base_url: str | None = None,
        event_key: str | None = None,
        is_production: bool | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.app_id = app_id
        self.base_url = base_url
        self.is_production = is_production or env.is_prod()
        self.logger = logger or logging.getLogger(__name__)

        if event_key is None:
            if not self.is_production:
                event_key = "NO_EVENT_KEY_SET"
            else:
                event_key = os.getenv(const.EnvKey.EVENT_KEY.value)
        if event_key is None:
            self.logger.error("missing event key")
            raise errors.MissingEventKey("missing event key")
        self._event_key = event_key

        event_origin = base_url
        if event_origin is None:
            if not self.is_production:
                self.logger.info("Defaulting event origin to Dev Server")
                event_origin = const.DEV_SERVER_ORIGIN
            else:
                event_origin = const.DEFAULT_EVENT_ORIGIN
        self._event_origin = event_origin

    async def send(
        self, events: event_lib.Event | list[event_lib.Event]
    ) -> list[str]:
        # TODO: Re-implement this method to be truly async.
        return self.send_sync(events)

    def send_sync(
        self, events: event_lib.Event | list[event_lib.Event]
    ) -> list[str]:
        url = urllib.parse.urljoin(self._event_origin, f"/e/{self._event_key}")
        headers = net.create_headers()

        if not isinstance(events, list):
            events = [events]

        body = []
        for event in events:
            d = event.to_dict()
            if d.get("id") == "":
                del d["id"]
            if d.get("ts") == 0:
                d["ts"] = int(time.time() * 1000)
            body.append(d)

        res = net.requests_session.post(
            url, json=body, headers=headers, timeout=30
        )
        res_body: object = res.json()
        if not isinstance(res_body, dict) or "ids" not in res_body:
            self.logger.error("unexpected response when sending events")
            raise errors.InvalidResponseShape(
                "unexpected response when sending events"
            )

        ids = res_body["ids"]
        if not isinstance(ids, list):
            self.logger.error("unexpected response when sending events")
            raise errors.InvalidResponseShape(
                "unexpected response when sending events"
            )

        return ids
