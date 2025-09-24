import typing
from urllib.parse import urljoin

from inngest._internal import errors, types
from inngest._internal.net import AuthenticatedHTTPClient


class _TokenResponse(types.BaseModel):
    jwt: str


async def get_subscription_token(
    http_client: AuthenticatedHTTPClient,
    api_origin: str,
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

    res = await http_client.post(
        url=urljoin(api_origin, "/v1/realtime/token"),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    if res.status_code != 201:
        raise errors.Error(
            "failed to get subscription token",
        )
    # Response is an object with a "jwt" property which is a string
    response_data = _TokenResponse.model_validate(res.json())

    # Return a dictionary ready to be used by the @inngest/realtime npm package
    return {
        "channel": channel,
        "topics": topics,
        "key": response_data.jwt,
    }


def get_subscription_token_sync(
    http_client: AuthenticatedHTTPClient,
    api_origin: str,
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

    res = http_client.post_sync(
        url=urljoin(api_origin, "/v1/realtime/token"),
        body=data,
    )
    if isinstance(res, Exception):
        raise res
    if res.status_code != 201:
        raise errors.Error(
            "failed to get subscription token",
        )
    # Response is an object with a "jwt" property which is a string
    response_data = _TokenResponse.model_validate(res.json())

    # Return a dictionary ready to be used by the @inngest/realtime npm package
    return {
        "channel": channel,
        "topics": topics,
        "key": response_data.jwt,
    }
