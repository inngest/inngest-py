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
    This currently requires the Step object as an argument as the API is finalized.
    """
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
