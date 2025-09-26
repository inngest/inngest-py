import typing
from urllib.parse import urljoin

from inngest._internal import client_lib, types


class _TokenResponse(types.BaseModel):
    jwt: str


async def get_subscription_token(
    client: client_lib.Inngest,
    channel: str,
    topics: list[str],
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
                "name": topic,
                "kind": "run",
            }
        )

    res = await client._http_client.post(
        url=urljoin(client._api_origin, "/v1/realtime/token"),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    # Response is an object with a "jwt" property which is a string
    response_data = _TokenResponse.model_validate(res.json())

    # Return a dictionary ready to be used by the @inngest/realtime npm package
    return {
        "channel": channel,
        "topics": topics,
        "key": response_data.jwt,
    }


def get_subscription_token_sync(
    client: client_lib.Inngest,
    channel: str,
    topics: list[str],
) -> typing.Mapping[str, object]:
    """
    Create a subscription token for a given channel and topics synchronously.
    The token can be used by a client to subscribe to realtime events,
    including front-end applications using the @inngest/realtime npm package.
    """
    data = []
    for topic in topics:
        data.append(
            {
                "channel": channel,
                "name": topic,
                "kind": "run",
            }
        )

    res = client._http_client.post_sync(
        url=urljoin(client._api_origin, "/v1/realtime/token"),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    # Response is an object with a "jwt" property which is a string
    response_data = _TokenResponse.model_validate(res.json())

    # Return a dictionary ready to be used by the @inngest/realtime npm package
    return {
        "channel": channel,
        "topics": topics,
        "key": response_data.jwt,
    }
