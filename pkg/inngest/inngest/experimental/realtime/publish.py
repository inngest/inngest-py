import json
import typing
from urllib.parse import urlencode, urljoin

from inngest._internal import errors, step_lib


# Q - Should this be step_publish or realtime publish or otherwise to compare to publish within a step?
# TODO - Support streams
async def publish(
    step: step_lib.Step,
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
        "run_id": step._run_id,
    }

    async def _publish_api_request() -> None:
        res = await step._client._post(
            url=urljoin(
                step._client._api_origin,
                f"/v1/realtime/publish?{urlencode(params)}",
            ),
            body=data,
        )
        if isinstance(res, Exception):
            raise res
        if res.status_code != 200:
            raise errors.Error(
                "failed to publish to realtime channel",
            )
        return None

    await step.run(f"publish:{channel}", _publish_api_request)

    return None
