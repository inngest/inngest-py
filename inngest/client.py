from logging import getLogger, Logger
import os
from time import time
from urllib.parse import urljoin

from .const import DEFAULT_EVENT_ORIGIN, DEV_SERVER_ORIGIN, EnvKey
from .env import allow_dev_server
from .errors import MissingEventKey
from .net import create_headers, Fetch
from .types import Event


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

    def send(self, data: Event | list[Event]) -> None:
        url = urljoin(self._event_origin, f"/e/{self._event_key}")
        headers = create_headers()

        if not isinstance(data, list):
            data = [data]

        events = []
        for d in data:
            event = d.to_dict()
            if event.get("id") == "":
                del event["id"]
            if event.get("ts") == 0:
                event["ts"] = int(time() * 1000)
            events.append(event)

        print(url)
        with Fetch.post(url, events, headers) as res:
            print(res.status)
