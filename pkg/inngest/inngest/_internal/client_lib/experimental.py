# from inngest.experimental.realtime.subscription_tokens import (
#     get_subscription_token,
# )
from inngest.experimental.realtime import publish

from .api import ApiClient


class Experimental:
    """A container for experimental features, available on the client."""

    def __init__(self, api_client: ApiClient):
        self._api_client = api_client

    async def publish(self, channel: str, topic: str, data: dict) -> None:
        await publish(self._api_client, channel, topic, data)

    # def get_subscription_token(self, channel: str, topics: list[str]):
    #     return get_subscription_token(self._client, channel, topics)
