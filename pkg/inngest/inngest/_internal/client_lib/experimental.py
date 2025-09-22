from inngest._internal.net import AuthenticatedHTTPClient
from inngest.experimental.realtime.subscription_tokens import (
    get_subscription_token,
)


class Experimental:
    """A container for experimental features, available on the client."""

    def __init__(self, http_client: AuthenticatedHTTPClient, api_origin: str):
        self._http_client = http_client
        self._api_origin = api_origin

    async def get_subscription_token(self, channel: str, topics: list[str]):
        """
        Create a subscription token for a given channel and topics.
        The token can be used by a client to subscribe to realtime events,
        including front-end applications using the @inngest/realtime npm package.
        """
        return await get_subscription_token(
            self._http_client, self._api_origin, channel, topics
        )
