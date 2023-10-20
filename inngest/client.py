from logging import getLogger, Logger
import os
from time import time
from urllib.parse import urljoin

from .const import DEFAULT_EVENT_ORIGIN, DEV_SERVER_ORIGIN, EnvKey
from .env import allow_dev_server
from .errors import InvalidResponseShape, MissingEventKey
from .event import Event
from .net import create_headers, requests_session


class Inngest:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        event_key: str | None = None,
        id: str,  # pylint: disable=redefined-builtin
        logger: Logger | None = None,
    ) -> None:
        self.id = id
        self._logger = logger or getLogger(__name__)

        if event_key is None:
            if allow_dev_server():
                event_key = "NO_EVENT_KEY_SET"
            else:
                event_key = os.getenv(EnvKey.EVENT_KEY.value)
        if event_key is None:
            self._logger.error("missing event key")
            raise MissingEventKey("missing event key")
        self._event_key = event_key

        event_origin = base_url
        if event_origin is None:
            if allow_dev_server():
                self._logger.info("Defaulting event origin to Dev Server")
                event_origin = DEV_SERVER_ORIGIN
            else:
                event_origin = DEFAULT_EVENT_ORIGIN
        self._event_origin = event_origin

    def send(self, events: Event | list[Event]) -> list[str]:
        url = urljoin(self._event_origin, f"/e/{self._event_key}")
        headers = create_headers()

        if not isinstance(events, list):
            events = [events]

        body = []
        for event in events:
            d = event.to_dict()
            if d.get("id") == "":
                del d["id"]
            if d.get("ts") == 0:
                d["ts"] = int(time() * 1000)
            body.append(d)

        res = requests_session.post(url, json=body, headers=headers, timeout=30)
        res_body: object = res.json()
        if not isinstance(res_body, dict) or "ids" not in res_body:
            self._logger.error("unexpected response when sending events")
            raise InvalidResponseShape("unexpected response when sending events")

        ids = res_body["ids"]
        if not isinstance(ids, list):
            self._logger.error("unexpected response when sending events")
            raise InvalidResponseShape("unexpected response when sending events")

        return ids
