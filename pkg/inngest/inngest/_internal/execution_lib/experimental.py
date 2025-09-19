from inngest._internal.client_lib.api import ApiClient
from inngest.experimental.realtime import publish


class ExperimentalContext:
    """A container for experimental features, available within function context."""

    def __init__(self, api_client: ApiClient):
        self._api_client = api_client

    async def publish(self, channel: str, topic: str, data: dict) -> None:
        """
        Publish a message to a realtime channel.
        This currently requires the Step object as an argument as the API is finalized.

        Args:
        ----
          channel: Realtime channel name
          topic: Realtime topic name
          data: Any data to publish to any active channel and topic subscribers
        """
        await publish(self._api_client, channel, topic, data)
