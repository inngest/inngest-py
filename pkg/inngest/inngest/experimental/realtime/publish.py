import json
import typing
from urllib.parse import urlencode, urljoin

from inngest._internal import errors
from inngest._internal.net import AuthenticatedHTTPClient


# TODO - Support streams
async def publish(
    http_client: AuthenticatedHTTPClient,
    api_origin: str,
    channel: str,
    topic: str,
    data: typing.Mapping[str, object],
) -> None:
    """
    Publish a message to a realtime channel.

    Args:
    ----
        http_client: The authenticated HTTP client
        api_origin: The API origin URL
        channel: The realtime channel name
        topic: The realtime topic name
        data: JSON-serializable data to publish to subscribers

    Raises:
    ------
        errors.Error: If data is not JSON serializable or if publishing fails
    """
    # Validate that data is JSON serializable
    try:
        json.dumps(data)
    except (TypeError, ValueError) as e:
        raise errors.Error(f"Data must be JSON serializable: {e}")

    params = {
        "channel": channel,
        "topic": topic,
    }

    res = await http_client.post(
        url=urljoin(api_origin, f"/v1/realtime/publish?{urlencode(params)}"),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    if res.status_code != 200:
        raise errors.Error(
            "failed to publish to realtime channel",
        )
    return None
