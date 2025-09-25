import typing
from urllib.parse import urlencode, urljoin

from inngest._internal import client_lib


# TODO - Support streams
async def publish(
    client: client_lib.Inngest,
    channel: str,
    topic: str,
    data: typing.Mapping[str, object],
) -> None:
    """
    Publish a message to a realtime channel.

    Args:
    ----
        client: The Inngest client
        channel: The realtime channel name
        topic: The realtime topic name
        data: JSON-serializable data to publish to subscribers

    Raises:
    ------
        errors.Error: If data is not JSON serializable or if publishing fails
    """

    params = {
        "channel": channel,
        "topic": topic,
    }

    res = await client._http_client.post(
        url=urljoin(
            client._api_origin, f"/v1/realtime/publish?{urlencode(params)}"
        ),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    return None


def publish_sync(
    client: client_lib.Inngest,
    channel: str,
    topic: str,
    data: typing.Mapping[str, object],
) -> None:
    """
    Publish a message to a realtime channel synchronously.

    Args:
    ----
        client: The Inngest client
        channel: The realtime channel name
        topic: The realtime topic name
        data: JSON-serializable data to publish to subscribers

    Raises:
    ------
        errors.Error: If data is not JSON serializable or if publishing fails
    """

    params = {
        "channel": channel,
        "topic": topic,
    }

    res = client._http_client.post_sync(
        url=urljoin(
            client._api_origin, f"/v1/realtime/publish?{urlencode(params)}"
        ),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    return None
