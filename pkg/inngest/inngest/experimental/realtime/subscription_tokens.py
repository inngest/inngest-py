import typing
from urllib.parse import urljoin

from inngest._internal import client_lib, errors


async def get_subscription_token(
    client: client_lib.Inngest, channel: str, topics: list[str]
) -> typing.Mapping[str, object]:
    """
    Create a subscription token for a given channel and topics.
    The token can be used by a client to subscribe to realtime events,
    including front-end applications using the @inngest/realtime npm package.
    """
    data = []
    for topic in topics:
        data.append(
            {
                "channel": channel,
                "topic": topic,
                "kind": "run",
            }
        )

    res = await client._post(
        url=urljoin(
            client._api_origin,
            "/v1/realtime/token",
        ),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    if res.status_code >= 300:
        raise errors.Error(
            "failed to get subscription token",
        )
    # Response is an object with a "jwt" property which is a string
    return res.json()
