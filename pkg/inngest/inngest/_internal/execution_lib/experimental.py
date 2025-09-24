import typing

from inngest._internal.net import AuthenticatedHTTPClient
from inngest.experimental.realtime import publish


class ExperimentalContext:
    """A container for experimental features, available within function context."""

    def __init__(self, http_client: AuthenticatedHTTPClient, api_origin: str):
        self._http_client = http_client
        self._api_origin = api_origin

    async def publish(
        self, *, channel: str, topic: str, data: typing.Mapping[str, object]
    ) -> None:
        """
        Publish a message to a realtime channel.

        Args:
        ----
          channel: Realtime channel name
          topic: Realtime topic name
          data: JSON-serializable data to publish to any active channel and topic subscribers
        """
        await publish(self._http_client, self._api_origin, channel, topic, data)
