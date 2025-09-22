from inngest.experimental.realtime.subscription_tokens import (
    get_subscription_token,
)

from .api import ApiClient


class Experimental:
    """A container for experimental features, available on the client."""

    def __init__(self, api_client: ApiClient):
        self._api_client = api_client

    async def get_subscription_token(self, channel: str, topics: list[str]):
        """
        Create a subscription token for a given channel and topics.
        The token can be used by a client to subscribe to realtime events,
        including front-end applications using the @inngest/realtime npm package.
        """
        return await get_subscription_token(self._api_client, channel, topics)
