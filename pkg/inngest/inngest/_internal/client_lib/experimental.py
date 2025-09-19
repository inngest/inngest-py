import typing
from urllib.parse import urlencode, urljoin

# from inngest.experimental.realtime import publish
# from inngest.experimental.realtime.subscription_tokens import (
#     get_subscription_token,
# )
# from .client import Inngest
# if typing.TYPE_CHECKING:
from inngest._internal import errors

from .api import ApiClient


class Experimental:
    """A container for experimental features, available on the client."""

    def __init__(self, api_client: ApiClient):
        self._api_client = api_client

    async def publish(self, channel: str, topic: str, data: dict) -> None:
        """
        Publish a message to a realtime channel.
        This currently requires the Step object as an argument as the API is finalized.
        """

        params = {
            "channel": channel,
            "topic": topic,
        }

        res = await self._api_client.post(
            url=f"/v1/realtime/publish?{urlencode(params)}",
            body=data,
        )
        if isinstance(res, Exception):
            raise res
        if res.status_code != 200:
            raise errors.Error(
                "failed to publish to realtime channel",
            )
        return None

        # return publish(self._client, channel, topic, data)

    # def get_subscription_token(self, channel: str, topics: list[str]):
    #     return get_subscription_token(self._client, channel, topics)
