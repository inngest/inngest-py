import typing

from inngest._internal.net import AuthenticatedHTTPClient
from inngest.experimental.realtime import (
    get_subscription_token,
    get_subscription_token_sync,
    publish,
    publish_sync,
)


class Experimental:
    """A container for experimental features, available on the client."""

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

    def publish_sync(
        self, *, channel: str, topic: str, data: typing.Mapping[str, object]
    ) -> None:
        """
        Publish a message to a realtime channel synchronously.

        Args:
        ----
          channel: Realtime channel name
          topic: Realtime topic name
          data: JSON-serializable data to publish to any active channel and topic subscribers
        """
        publish_sync(self._http_client, self._api_origin, channel, topic, data)

    async def get_subscription_token(
        self, channel: str, topics: list[str]
    ) -> typing.Mapping[str, object]:
        """
        Create a subscription token for a given channel and topics.
        The token can be used by a client to subscribe to realtime events,
        including front-end applications using the @inngest/realtime npm package.
        """
        return await get_subscription_token(
            self._http_client, self._api_origin, channel, topics
        )

    def get_subscription_token_sync(
        self, channel: str, topics: list[str]
    ) -> typing.Mapping[str, object]:
        """
        Create a subscription token for a given channel and topics synchronously.
        The token can be used by a client to subscribe to realtime events,
        including front-end applications using the @inngest/realtime npm package.
        """
        return get_subscription_token_sync(
            self._http_client, self._api_origin, channel, topics
        )
